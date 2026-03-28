"""SSH tunnel support for PostgreSQL connections.

Starts an SSH tunnel when QUART_POSTGRES_SSH_HOST is set, forwarding
localhost:<local_port> → QUART_POSTGRES_HOST:QUART_POSTGRES_PORT through
the bastion. The app then connects to localhost instead of the real host.

Required env vars (when tunneling is active):
    QUART_POSTGRES_SSH_HOST      Bastion / jump host hostname or IP
    QUART_POSTGRES_SSH_KEY_FILE  Path to private key file (default: ~/.ssh/id_rsa)

Optional:
    QUART_POSTGRES_SSH_USER      SSH username (default: current OS user)
"""

import logging
import os
import select
import socketserver
import threading
from getpass import getuser
from typing import Any, Optional

import paramiko

logger = logging.getLogger(__name__)


class _ForwardHandler(socketserver.BaseRequestHandler):
    """Handles a single forwarded TCP connection through the SSH transport."""

    def handle(self) -> None:
        server: Any = self.server
        try:
            chan = server.ssh_transport.open_channel(
                "direct-tcpip",
                server.remote_bind_address,
                self.request.getpeername(),
            )
        except Exception as exc:
            transport: paramiko.Transport = server.ssh_transport
            if not transport.is_active() and server.tunnel is not None:
                # Transport is dead – attempt to reconnect the SSH client.
                logger.warning("SSH tunnel: transport dead, triggering reconnect")
                server.tunnel._reconnect()
                # Try one more time with the (hopefully) new transport.
                try:
                    chan = server.ssh_transport.open_channel(
                        "direct-tcpip",
                        server.remote_bind_address,
                        self.request.getpeername(),
                    )
                except Exception as exc2:
                    logger.warning(
                        "SSH tunnel: channel open failed after reconnect: %s", exc2
                    )
                    return
            else:
                logger.warning("SSH tunnel: failed to open channel: %s", exc)
                return

        try:
            while True:
                r, _, _ = select.select([self.request, chan], [], [], 5.0)
                if self.request in r:
                    data = self.request.recv(4096)
                    if not data:
                        break
                    chan.sendall(data)
                if chan in r:
                    data = chan.recv(4096)
                    if not data:
                        break
                    self.request.sendall(data)
        except (OSError, EOFError, paramiko.SSHException):
            pass  # connection reset or closed by peer – not an error
        finally:
            chan.close()
            self.request.close()


class _ForwardServer(socketserver.ThreadingTCPServer):
    """Local TCP server that forwards connections via an SSH transport."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        local_addr: tuple[str, int],
        ssh_transport: paramiko.Transport,
        remote_bind_address: tuple[str, int],
        tunnel: "SSHTunnel",
    ) -> None:
        self.ssh_transport = ssh_transport
        self.remote_bind_address = remote_bind_address
        self.tunnel = tunnel
        super().__init__(local_addr, _ForwardHandler)


class SSHTunnel:
    """Manages an SSH port-forwarding tunnel for database connections."""

    def __init__(self) -> None:
        self._client: Optional[paramiko.SSHClient] = None
        self._server: Optional[_ForwardServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._local_port: int = 0
        # SSH connection parameters saved on first start() for reconnects.
        self._ssh_host: str = ""
        self._ssh_user: str = ""
        self._ssh_key_file: str = ""
        self._remote_host: str = ""
        self._remote_port: int = 5432
        self._reconnect_lock = threading.Lock()

    @property
    def is_active(self) -> bool:
        return self._server is not None

    @property
    def local_bind_host(self) -> str:
        """Always '127.0.0.1' – the host psycopg should connect to."""
        return "127.0.0.1"

    @property
    def local_bind_port(self) -> int:
        """The OS-assigned local port for the tunnel."""
        if self._server is None:
            raise RuntimeError("SSH tunnel has not been started yet.")
        return self._local_port

    def start(self) -> bool:
        """Start tunnel if QUART_POSTGRES_SSH_HOST is set.

        Returns True when started, False when tunneling is not configured.
        """
        ssh_host = os.environ.get("QUART_POSTGRES_SSH_HOST")
        if not ssh_host:
            return False

        remote_pg_host = os.environ.get("QUART_POSTGRES_HOST", "localhost")
        remote_pg_port = int(os.environ.get("QUART_POSTGRES_PORT", "5432"))
        ssh_user = os.environ.get("QUART_POSTGRES_SSH_USER", getuser())
        ssh_key_file = os.path.expanduser(
            os.environ.get("QUART_POSTGRES_SSH_KEY_FILE", "~/.ssh/id_rsa")
        )

        if not os.path.isfile(ssh_key_file):
            raise ValueError(
                f"SSH tunnel: private key file not found at '{ssh_key_file}'. "
                "Set QUART_POSTGRES_SSH_KEY_FILE to a valid path."
            )

        logger.info(
            "Starting SSH tunnel -> %s:%s via %s@%s",
            remote_pg_host,
            remote_pg_port,
            ssh_user,
            ssh_host,
        )

        # Save connection params for potential reconnect later.
        self._ssh_host = ssh_host
        self._ssh_user = ssh_user
        self._ssh_key_file = ssh_key_file
        self._remote_host = remote_pg_host
        self._remote_port = remote_pg_port

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            ssh_host,
            username=ssh_user,
            key_filename=ssh_key_file,
            allow_agent=True,
            look_for_keys=False,
        )

        transport = self._client.get_transport()
        transport.set_keepalive(
            30
        )  # Send SSH keepalive every 30 s to prevent idle disconnect
        self._server = _ForwardServer(
            ("127.0.0.1", 0),
            transport,
            (remote_pg_host, remote_pg_port),
            self,
        )
        self._local_port = self._server.server_address[1]

        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="ssh-tunnel",
        )
        self._server_thread.start()
        logger.info("SSH tunnel active – local bind port: %s", self._local_port)
        return True

    def _reconnect(self) -> None:
        """Reconnect SSH client after transport failure. Thread-safe."""
        with self._reconnect_lock:
            # Re-check under lock – another thread may have already reconnected.
            if self._client is not None:
                t = self._client.get_transport()
                if t is not None and t.is_active():
                    return

            logger.warning(
                "SSH tunnel: reconnecting to %s@%s", self._ssh_user, self._ssh_host
            )
            try:
                if self._client is not None:
                    try:
                        self._client.close()
                    except Exception:
                        pass
                    self._client = None

                new_client = paramiko.SSHClient()
                new_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                new_client.connect(
                    self._ssh_host,
                    username=self._ssh_user,
                    key_filename=self._ssh_key_file,
                    allow_agent=True,
                    look_for_keys=False,
                )
                new_transport = new_client.get_transport()
                new_transport.set_keepalive(30)

                self._client = new_client
                # Update the _ForwardServer so new channels use the fresh transport.
                if self._server is not None:
                    self._server.ssh_transport = new_transport

                logger.info("SSH tunnel: reconnected successfully")
            except Exception as exc:
                logger.error("SSH tunnel: reconnect failed: %s", exc)

    def stop(self) -> None:
        """Stop the tunnel and close the SSH connection."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._server_thread is not None:
            self._server_thread.join(timeout=5)
            self._server_thread = None
        if self._client is not None:
            logger.info("Stopping SSH tunnel.")
            self._client.close()
            self._client = None


# Module-level singleton – imported by the Quart app factory
tunnel = SSHTunnel()
