"""Install the user-scoped MLSpace plugin through each client's own CLI."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MARKETPLACE_SOURCE = 'https://github.com/noesskeetit/mlspace-plugin.git'
PLUGIN_ID = 'mlspace@mlspace'


@dataclass(frozen=True)
class NativePluginStatus:
    client: str
    installed: bool = False
    enabled: bool = False
    version: str | None = None
    marketplace_source: str | None = None
    plugin_root: Path | None = None


def _run(client: str, executable: str, args: list[str], *, json_output: bool = False) -> Any:
    if client == 'codex' and (home := os.environ.get('CODEX_HOME')):
        try:
            Path(home).expanduser().mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            raise ValueError(f'codex: cannot create CODEX_HOME at {home}. '
                             'Check that it is a writable directory and retry setup.') from exc
    try:
        result = subprocess.run(
            [executable, *args], check=True, capture_output=True, text=True, timeout=180,
            cwd=Path.home(), stdin=subprocess.DEVNULL, env={k: v for k, v in os.environ.items() if not k.startswith('MLSPACE_')},
        )
        return json.loads(result.stdout) if json_output else None
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError(f'{client}: plugin command failed or returned an unsupported response. '
                         'Check network access and update the client, then retry setup. '
                         'Client output suppressed because it can contain secrets.') from exc


def inspect_native(client: str, executable: str) -> NativePluginStatus:
    """Read state before changing anything; never adopt another marketplace."""
    if client not in ('claude-code', 'codex'):
        raise ValueError('Not a native plugin client: ' + client)
    markets = _run(client, executable, ['plugin', 'marketplace', 'list', '--json'], json_output=True)
    plugins = _run(client, executable, ['plugin', 'list', '--json'], json_output=True)
    try:
        if client == 'codex':
            markets, plugins = markets['marketplaces'], plugins['installed']
        if not isinstance(markets, list) or not isinstance(plugins, list):
            raise TypeError
        matches = [row for row in markets if row['name'] == 'mlspace']
        if len(matches) > 1:
            raise TypeError
        source = None
        if matches:
            market = matches[0]
            if client == 'claude-code':
                kind, source = market['source'], market.get('url')
            else:
                kind = market['marketplaceSource']['sourceType']
                source = market['marketplaceSource']['source']
            if kind != 'git' or source != MARKETPLACE_SOURCE:
                raise ValueError(f'{client}: marketplace mlspace has a different source; '
                                 'remove or rename that marketplace before setup.')
        id_key = 'id' if client == 'claude-code' else 'pluginId'
        selected = [row for row in plugins if row[id_key] == PLUGIN_ID]
        if any('mlspace' in row[id_key].lower() and row[id_key] != PLUGIN_ID for row in plugins):
            raise ValueError(f'{client}: another MLSpace plugin is installed; resolve it before setup.')
        if not selected:
            return NativePluginStatus(client, marketplace_source=source)
        if len(selected) != 1 or (client == 'claude-code' and selected[0]['scope'] != 'user'):
            raise ValueError(f'{client}: MLSpace is installed outside the user scope; resolve it before setup.')
        row = selected[0]
        if source is None:
            raise ValueError(f'{client}: installed MLSpace plugin has no verifiable marketplace source.')
        version, enabled = row['version'], row['enabled']
        if not isinstance(version, str) or not isinstance(enabled, bool):
            raise TypeError
        root = None
        if client == 'claude-code':
            root = Path(row['installPath'])
        elif enabled:
            server = _run(client, executable, ['mcp', 'get', 'mlspace', '--json'], json_output=True)
            root = Path(server['transport']['env']['PLUGIN_ROOT'])
        if root is not None and (not root.is_absolute() or not root.is_dir()):
            raise TypeError
        return NativePluginStatus(client, True, enabled, version, source, root)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'{client}: unsupported plugin state; update the client and retry setup.') from exc


def install_native(client: str, executable: str, expected_version: str) -> NativePluginStatus:
    status = inspect_native(client, executable)
    if status.installed and not status.enabled:
        raise ValueError(f'{client}: MLSpace plugin is disabled. Enable {PLUGIN_ID} in the client and retry setup.')
    if status.installed and status.version == expected_version:
        return status
    claude = client == 'claude-code'
    if status.marketplace_source is None:
        _run(client, executable, ['plugin', 'marketplace', 'add', MARKETPLACE_SOURCE,
                                 *(['--scope', 'user'] if claude else ['--json'])])
    else:
        _run(client, executable, ['plugin', 'marketplace', 'update' if claude else 'upgrade',
                                 'mlspace', *([] if claude else ['--json'])])
    action = ('update' if status.installed else 'install') if claude else 'add'
    _run(client, executable, ['plugin', action, PLUGIN_ID,
                             *(['--scope', 'user'] if claude else []), '--json'])
    result = inspect_native(client, executable)
    if not result.installed or not result.enabled or result.version != expected_version:
        raise ValueError(f'{client}: expected MLSpace {expected_version} was not confirmed. '
                         'Retry with uvx mlspace-plugin@latest setup --force after the release is available.')
    return result
