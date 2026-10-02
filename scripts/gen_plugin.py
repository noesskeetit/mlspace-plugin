"""Generate the plugin manifests in ``plugin/`` from the package itself.

Skills in ``plugin/skills/*/SKILL.md`` are hand-written sources. Manifests are
derived: their version tracks ``mlspace_mcp.__version__`` and every client config
launches that exact version from PyPI. ``tests/test_plugin_bundle.py``
runs this module with ``--check`` and fails when a manifest on disk differs.

Spec: https://github.com/agentplugins/agent-plugins-spec (v1.0.0)
      https://agentskills.io/specification (SKILL.md)

Usage:
    python scripts/gen_plugin.py            # write the manifests
    python scripts/gen_plugin.py --check    # exit 1 if a manifest is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mlspace_mcp import __version__  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"

SPEC = "1.0.0"
PLUGIN_SCHEMA = f"https://agent-plugins.org/schemas/{SPEC}/plugin.schema.json"
MCP_SCHEMA = f"https://agent-plugins.org/schemas/{SPEC}/mcp.schema.json"

def build() -> dict[str, str]:
    """Return the generated manifests as {relative path: content}."""
    identity = {
        "name": "mlspace",
        "version": __version__,
        "description": (
            "Cloud.ru MLSpace: training jobs, inference, notebooks, data transfer, "
            "registry and compute catalog — an MCP server plus skills."
        ),
    }
    metadata = {
        **identity,
        "author": {"name": "Cloud.ru"},
        "homepage": "https://cloud.ru/docs/aicloud/mlspace",
        "license": "MIT",
        "keywords": ["mlspace", "cloud.ru", "mlops", "training", "inference", "gpu"],
    }
    manifests = {
        "plugin.json": {"$schema": PLUGIN_SCHEMA, **metadata},
        ".codex-plugin/plugin.json": {
            **identity,
            "author": {"name": "Cloud.ru"},
            "skills": "./skills/",
            "mcpServers": "./.mcp.json",
            "interface": {
                "displayName": "MLSpace",
                "shortDescription": "Manage Cloud.ru MLSpace with MCP and skills",
                "longDescription": identity["description"],
                "developerName": "Cloud.ru",
                "category": "Developer tools",
                "capabilities": ["Read", "Write"],
                "defaultPrompt": ["Show jobs across my selected MLSpace workspaces."],
            },
        },
        ".claude-plugin/plugin.json": metadata,
    }
    for filename in ("mcp.json", ".mcp.json"):
        manifests[filename] = {
            **({"$schema": MCP_SCHEMA} if filename == "mcp.json" else {}),
            "mcpServers": {
                "mlspace": {
                    "type": "stdio",
                    "command": "uvx",
                    # Server and skills always come from the same release.
                    "args": [
                        "--from",
                        f"mlspace-plugin=={__version__}",
                        "mlspace-plugin", "--transport", "stdio",
                    ],
                }
            },
        }
    return {
        name: json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        for name, manifest in manifests.items()
    }


def build_marketplaces() -> dict[str, str]:
    marketplaces = {
        ".agents/plugins/marketplace.json": {
            "name": "mlspace", "interface": {"displayName": "MLSpace"},
            "plugins": [{"name": "mlspace", "source": {"source": "local", "path": "./plugin"},
                         "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                         "category": "Productivity"}],
        },
        ".claude-plugin/marketplace.json": {
            "name": "mlspace", "owner": {"name": "Cloud.ru"},
            "plugins": [{"name": "mlspace", "source": "./plugin"}],
        },
    }
    return {name: json.dumps(data, indent=2) + "\n" for name, data in marketplaces.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify plugin/ matches; do not write")
    args = ap.parse_args(argv)

    plugin_files = build()
    files = {f'plugin/{name}': content for name, content in plugin_files.items()} | build_marketplaces()

    if args.check:
        stale = [
            rel
            for rel, want in files.items()
            if not (ROOT / rel).is_file() or (ROOT / rel).read_text() != want
        ]
        expected = {ROOT / rel for rel in files} | {PLUGIN / "README.md"}
        extra = [
            str(p.relative_to(PLUGIN))
            for p in PLUGIN.rglob("*")
            if p.is_file() and p not in expected
            and not (p.parent.parent == PLUGIN / "skills" and p.name == "SKILL.md")
        ]
        if stale or extra:
            for rel in stale:
                print(f"stale: {rel}", file=sys.stderr)
            for rel in extra:
                print(f"unexpected: plugin/{rel}", file=sys.stderr)
            print("run: python scripts/gen_plugin.py", file=sys.stderr)
            return 1
        print(f"plugin/ manifests are up to date ({len(files)} files)")
        return 0

    for rel, content in files.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    print(f"wrote {len(files)} manifests to {PLUGIN.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
