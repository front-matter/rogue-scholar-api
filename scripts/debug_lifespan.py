import asyncio
import os

from quart.testing.app import TestApp


async def main() -> None:
    # Expect env vars to be set externally.
    print("DB host:", os.getenv("QUART_POSTGRES_HOST"))
    from api import app  # import after env vars

    ta = TestApp(app, startup_timeout=2, shutdown_timeout=2)
    try:
        await ta.startup()
        print("startup complete")
        await ta.shutdown()
        print("shutdown complete")
    except Exception as exc:
        print("lifespan error:", repr(exc))
        task = getattr(ta, "_task", None)
        print("task:", task)
        if task is not None:
            print("task done:", task.done())
            if task.done():
                try:
                    print("task exception:", repr(task.exception()))
                except Exception as inner:
                    print("task.exception() raised:", repr(inner))
        raise


if __name__ == "__main__":
    asyncio.run(main())
