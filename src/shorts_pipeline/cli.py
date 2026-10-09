"""CLI entrypoints."""

from __future__ import annotations

import argparse
import sys

from shorts_pipeline import __version__
from shorts_pipeline.logging_setup import setup_logging
from shorts_pipeline.security import generate_fernet_key


def main(argv: list[str] | None = None) -> int:
    """shorts-pipeline CLI."""
    parser = argparse.ArgumentParser(prog="shorts-pipeline")
    parser.add_argument("--version", action="store_true", help="Print version")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gen-fernet-key", help="Generate a Fernet key for .env")

    serve = sub.add_parser("serve", help="Run the FastAPI server")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    if args.command == "gen-fernet-key":
        print(generate_fernet_key())
        return 0

    if args.command == "serve":
        import uvicorn

        from shorts_pipeline.config import get_settings

        settings = get_settings()
        setup_logging(log_level=settings.log_level, json_logs=settings.log_json)
        host = args.host or settings.api_host
        port = args.port or settings.api_port
        uvicorn.run(
            "shorts_pipeline.api.app:app",
            host=host,
            port=port,
            reload=settings.app_env == "development",
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
