"""Tests for api/ssh_tunnel.py

Run with:
    uv run pytest tests/test_ssh_tunnel.py -v
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(local_port: int = 15432):
    """Return a mock SSHClient and a mock _ForwardServer."""
    mock_client = MagicMock()
    mock_transport = MagicMock()
    mock_client.get_transport.return_value = mock_transport

    mock_server = MagicMock()
    mock_server.server_address = ("127.0.0.1", local_port)
    return mock_client, mock_server


# ---------------------------------------------------------------------------
# start() – no tunnel when SSH host is absent
# ---------------------------------------------------------------------------


def test_start_no_op_when_ssh_host_not_set(monkeypatch):
    monkeypatch.setenv("QUART_POSTGRES_SSH_HOST", "")

    from api.ssh_tunnel import SSHTunnel

    t = SSHTunnel()
    result = t.start()

    assert result is False
    assert not t.is_active


# ---------------------------------------------------------------------------
# start() – raises when key file does not exist
# ---------------------------------------------------------------------------


def test_start_raises_without_key_file(monkeypatch, tmp_path):
    monkeypatch.setenv("QUART_POSTGRES_SSH_HOST", "bastion.example.com")
    monkeypatch.setenv("QUART_POSTGRES_SSH_KEY_FILE", str(tmp_path / "missing_key"))

    from api.ssh_tunnel import SSHTunnel

    t = SSHTunnel()
    with pytest.raises(ValueError, match="private key file not found"):
        t.start()


# ---------------------------------------------------------------------------
# start() – happy path with key file
# ---------------------------------------------------------------------------


def test_start_with_key_file(monkeypatch, tmp_path):
    key_file = tmp_path / "id_ed25519"
    key_file.write_text("dummy")

    monkeypatch.setenv("QUART_POSTGRES_SSH_HOST", "bastion.example.com")
    monkeypatch.setenv("QUART_POSTGRES_SSH_USER", "ubuntu")
    monkeypatch.setenv("QUART_POSTGRES_SSH_KEY_FILE", str(key_file))
    monkeypatch.setenv("QUART_POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("QUART_POSTGRES_PORT", "5432")

    mock_client, mock_server = _make_mock_client(local_port=15432)

    with (
        patch("api.ssh_tunnel.paramiko.SSHClient", return_value=mock_client),
        patch("api.ssh_tunnel._ForwardServer", return_value=mock_server),
    ):
        from api.ssh_tunnel import SSHTunnel

        t = SSHTunnel()
        result = t.start()

    assert result is True
    assert t.local_bind_host == "127.0.0.1"
    assert t.local_bind_port == 15432
    mock_client.connect.assert_called_once_with(
        "bastion.example.com",
        username="ubuntu",
        key_filename=str(key_file),
        allow_agent=True,
        look_for_keys=False,
    )


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


def test_stop_calls_tunnel_stop(monkeypatch, tmp_path):
    key_file = tmp_path / "id_ed25519"
    key_file.write_text("dummy")

    monkeypatch.setenv("QUART_POSTGRES_SSH_HOST", "bastion.example.com")
    monkeypatch.setenv("QUART_POSTGRES_SSH_KEY_FILE", str(key_file))

    mock_client, mock_server = _make_mock_client()

    with (
        patch("api.ssh_tunnel.paramiko.SSHClient", return_value=mock_client),
        patch("api.ssh_tunnel._ForwardServer", return_value=mock_server),
    ):
        from api.ssh_tunnel import SSHTunnel

        t = SSHTunnel()
        t.start()
        t.stop()

    mock_server.shutdown.assert_called_once()
    mock_client.close.assert_called_once()
    assert t._server is None
    assert t._client is None


def test_stop_is_noop_when_not_started():
    from api.ssh_tunnel import SSHTunnel

    t = SSHTunnel()
    t.stop()  # should not raise


# ---------------------------------------------------------------------------
# local_bind_port before start()
# ---------------------------------------------------------------------------


def test_local_bind_port_before_start_raises():
    from api.ssh_tunnel import SSHTunnel

    t = SSHTunnel()
    with pytest.raises(RuntimeError, match="has not been started"):
        _ = t.local_bind_port
