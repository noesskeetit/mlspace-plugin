"""CLI entry point for mlspace-plugin."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import __version__
from .config import load_settings, user_config_file
from .server import build_server


def _configure_logging() -> None:
    """Basic stderr logging so the server's logger.warning/exception emit in prod.
    Level via MLSPACE_LOG_LEVEL (default INFO). stderr keeps stdout clean for stdio MCP.
    """
    level = os.environ.get("MLSPACE_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mlspace-plugin",
        description="MCP server for the Cloud.ru MLSpace public API v2.",
    )
    parser.add_argument("--version", action="version", version=f"mlspace-plugin {__version__}")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        help="Override MLSPACE_TRANSPORT.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print the tools that would be registered, then exit (no credentials needed).",
    )
    # Optional subcommand: with none given the CLI serves, as it always has.
    sub = parser.add_subparsers(dest="command")
    setup = sub.add_parser(
        "setup",
        help="Set up access keys, workspaces, MCP clients and skills.",
        description=(
            "Ask for Cloud.ru Key ID and Key Secret, discover MLSpace workspaces, and write them to "
            f"{user_config_file()} with mode 600. Runs in your terminal: the values "
            "are never sent to a model."
        ),
    )
    setup.add_argument("--path", type=Path, help="Write somewhere else than the user config.")
    setup.add_argument("--force", action="store_true", help="Overwrite an existing file.")
    setup.add_argument(
        "--base-url",
        help="MLSpace API endpoint to save (defaults to production or the existing target).",
    )
    setup.add_argument(
        "--no-verify", action="store_true", help="Save unverified config offline; requires --config-only and --workspace."
    )
    setup.add_argument("--client", dest="clients", action="append", choices=["claude-code", "codex", "opencode"], help="Connect this client (repeat for several); default: auto-detect.")
    setup.add_argument("--client-path", dest="client_paths", action="append", metavar="CLIENT=PATH", help="Explicit client executable when not in PATH.")
    setup.add_argument("--config-only", action="store_true", help="Only configure credentials/workspaces; do not register clients or skills.")
    setup.add_argument("--non-interactive", action="store_true", help="Never prompt; require explicit workspace IDs and credential source or saved keys.")
    setup.add_argument("--from-env", action="store_true", help="Use MLSPACE_CLIENT_ID / MLSPACE_CLIENT_SECRET from the environment.")
    setup.add_argument("--credentials-file", type=Path, help="Import keys from an existing dotenv file without printing them.")
    setup.add_argument("--replace-credentials", action="store_true", help="Ask for new keys instead of reusing saved keys.")
    setup.add_argument("--workspace", dest="workspace_ids", action="append", help="Exact workspace ID to select (repeat for several).")
    setup.add_argument("--ca-file", type=Path, help="Trusted corporate CA PEM; a copy is saved for subsequent MCP launches.")
    setup.add_argument("--list-workspaces", action="store_true", help="Return a bounded JSON list without saving or installing anything.")
    setup.add_argument("--search", default="", help="Filter workspace JSON by name, project or ID.")
    setup.add_argument("--offset", type=int, default=0)
    setup.add_argument("--limit", type=int, default=20, help="Workspace JSON page size (1–100).")
    args = parser.parse_args(argv)

    if args.command == "setup":
        from .init_cli import run_init

        return run_init(
            args.path,
            force=args.force,
            verify=not args.no_verify,
            base_url=args.base_url,
            config_only=args.config_only, non_interactive=args.non_interactive,
            from_env=args.from_env, credentials_file=args.credentials_file,
            workspace_ids=args.workspace_ids, clients=args.clients, client_paths=args.client_paths,
            ca_file=args.ca_file, replace_credentials=args.replace_credentials,
            list_workspaces=args.list_workspaces, search=args.search, offset=args.offset, limit=args.limit,
        )

    _configure_logging()
    settings = load_settings()
    if args.transport:
        settings.transport = args.transport

    if args.list_tools:
        mcp = build_server(settings)
        tools = mcp._tool_manager.list_tools()
        mode = "read-only" if settings.readonly else "read-write"
        print(f"mlspace-plugin {__version__} — {len(tools)} tools ({mode}):")
        for tool in sorted(tools, key=lambda t: t.name):
            print(f"  {tool.name}")
        return 0

    settings.validate_bind()
    settings.require_credentials()
    mcp = build_server(settings)

    if settings.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        print(
            f"mlspace-plugin serving streamable-HTTP on "
            f"http://{settings.host}:{settings.port}/mcp",
            file=sys.stderr,
        )
        mcp.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
