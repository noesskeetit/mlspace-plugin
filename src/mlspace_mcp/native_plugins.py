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
            raise ValueError(f'codex: не удалось создать каталог CODEX_HOME: {home}. '
                             'Проверьте, что путь указывает на каталог с правом записи, затем повторите setup.') from exc
    try:
        result = subprocess.run(
            [executable, *args], check=True, capture_output=True, text=True, timeout=180,
            cwd=Path.home(), stdin=subprocess.DEVNULL, env={k: v for k, v in os.environ.items() if not k.startswith('MLSPACE_')},
        )
        return json.loads(result.stdout) if json_output else None
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError(f'{client}: команда управления плагином завершилась ошибкой или вернула неподдерживаемый ответ. '
                         'Проверьте доступ к сети и обновите клиент, затем повторите setup. '
                         'Вывод клиента скрыт, поскольку может содержать секреты.') from exc


def inspect_native(client: str, executable: str) -> NativePluginStatus:
    """Read state before changing anything; never adopt another marketplace."""
    if client not in ('claude-code', 'codex'):
        raise ValueError('Клиент не поддерживает этот способ установки нативного плагина: ' + client)
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
                raise ValueError(f'{client}: у marketplace mlspace другой источник; '
                                 'перед setup удалите или переименуйте этот marketplace в клиенте.')
        id_key = 'id' if client == 'claude-code' else 'pluginId'
        selected = [row for row in plugins if row[id_key] == PLUGIN_ID]
        if any('mlspace' in row[id_key].lower() and row[id_key] != PLUGIN_ID for row in plugins):
            raise ValueError(f'{client}: уже установлен другой плагин MLSpace. Разрешите конфликт в клиенте перед setup.')
        if not selected:
            return NativePluginStatus(client, marketplace_source=source)
        if len(selected) != 1 or (client == 'claude-code' and selected[0]['scope'] != 'user'):
            raise ValueError(f'{client}: MLSpace установлен вне области user. Разрешите конфликт областей установки в клиенте перед setup.')
        row = selected[0]
        if source is None:
            raise ValueError(f'{client}: не удалось подтвердить источник marketplace установленного плагина MLSpace. Проверьте установку плагина в клиенте.')
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
        raise ValueError(f'{client}: состояние плагина не поддерживается. Обновите клиент и повторите setup.') from exc


def install_native(client: str, executable: str, expected_version: str) -> NativePluginStatus:
    status = inspect_native(client, executable)
    if status.installed and not status.enabled:
        raise ValueError(f'{client}: плагин MLSpace выключен. Включите {PLUGIN_ID} в клиенте и повторите setup.')
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
        raise ValueError(f'{client}: не удалось подтвердить ожидаемую версию MLSpace {expected_version}. '
                         'После появления релиза выполните uvx mlspace-plugin@latest setup --force.')
    return result
