"""User-scoped client registration and packaged skill installation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from . import __version__
from .config import credential_pointer_file
from .jsonc import loads as load_jsonc
from .jsonc import set_member as set_jsonc_member
from .native_plugins import inspect_native, install_native

CLIENTS = {'claude-code': 'claude', 'codex': 'codex', 'opencode': 'opencode'}


def install_state_file() -> Path:
    return credential_pointer_file().parent / 'install-state.json'


def detect_clients() -> dict[str, str]:
    return {name: path for name, executable in CLIENTS.items()
            if (path := shutil.which(executable))}


def server_command() -> list[str]:
    source = Path(__file__).resolve()
    # Package-index installs may run inside an evictable `uvx` environment.
    # Pin the runtime to the skills version, never to a cache directory or latest.
    cached = any(re.fullmatch(r'archive-v\d+', part) for part in source.parts)
    if cached and 'site-packages' in source.parts and (uvx := shutil.which('uvx')):
        if any(source.parent.parent.glob('mlspace_plugin-*.dist-info/direct_url.json')):
            raise ValueError('For a local wheel, use `uv tool install /path/to/package.whl` '
                             'before setup, or use setup --config-only for a native plugin.')
        return [uvx, '--from', f'mlspace-plugin=={__version__}',
                'mlspace-plugin', '--transport', 'stdio']
    executable = Path(sys.executable).parent / 'mlspace-plugin'
    if not executable.is_file():
        raise ValueError('Install the package with `uv tool install .` before connecting clients.')
    # An editable installation under /tmp disappears on reboot; reject that source.
    if source.is_relative_to(Path(tempfile.gettempdir()).resolve()) or str(source).startswith('/tmp/'):
        raise ValueError('Temporary installation: install the wheel with `uv tool install` first.')
    return [str(executable.absolute()), '--transport', 'stdio']


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    if path.is_symlink():
        raise ValueError(f'Refusing to replace a symlink: {path}')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _skill_sources() -> dict[str, str]:
    bundled = files('mlspace_mcp').joinpath('skills')
    # Editable installs use the very same versioned source that goes into the wheel.
    source = Path(__file__).resolve().parents[2] / 'plugin/skills'
    root = bundled if bundled.is_dir() else source
    result = {item.name: item.joinpath('SKILL.md').read_text(encoding='utf-8')
              for item in root.iterdir() if item.is_dir() and item.joinpath('SKILL.md').is_file()}
    if not result:
        raise ValueError('No packaged skills found; reinstall the MLSpace wheel.')
    return result


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _config(client: str) -> Path:
    if client == 'claude-code':
        custom = os.environ.get('CLAUDE_CONFIG_DIR')
        return Path(custom) / '.claude.json' if custom else Path.home() / '.claude.json'
    if client == 'codex':
        return Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
    explicit = os.environ.get('OPENCODE_CONFIG')
    if explicit:
        return Path(explicit).expanduser().absolute()
    root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'opencode'
    jsonc, plain = root / 'opencode.jsonc', root / 'opencode.json'
    if jsonc.exists() and plain.exists():
        raise ValueError('Both opencode.json and opencode.jsonc exist; select OPENCODE_CONFIG explicitly.')
    return jsonc if jsonc.exists() else plain


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if path.suffix == '.toml':
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib
        return dict(tomllib.loads(path.read_text()))
    return load_jsonc(path.read_text())


def managed_clients(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Find surviving managed registrations so one product updates together."""
    state_path = install_state_file()
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    detected = detect_clients()
    result = {}
    for client in state.get('clients', {}):
        if client not in CLIENTS:
            continue
        config = _config(client)
        previous_path = Path(state.get('configs', {}).get(client, str(config)))
        if client == 'opencode' and 'mlspace' not in _read_config(previous_path).get('mcp', {}):
            continue  # The user removed this connection; never recreate it.
        if previous_path.absolute() != config.absolute():
            variable = {'claude-code': 'CLAUDE_CONFIG_DIR', 'codex': 'CODEX_HOME',
                        'opencode': 'OPENCODE_CONFIG'}[client]
            raise ValueError(f'Previously connected {client} uses {previous_path}. '
                             f'Restore its {variable} setting before updating all MLSpace clients.')
        candidates = [(overrides or {}).get(client), state.get('executables', {}).get(client),
                      detected.get(client)]
        executable = next((path for path in candidates if path and Path(path).is_file()
                           and os.access(path, os.X_OK)), None)
        if not executable and client != 'opencode':
            raise ValueError(f'Previously connected {client} executable is unavailable. Restore it or use '
                             f'--client-path {client}=/absolute/path before updating MLSpace.')
        if client != 'opencode' and not inspect_native(client, executable or CLIENTS[client]).installed:
            continue
        result[client] = executable or CLIENTS[client]  # OpenCode config is written directly.
    return result


def prepare_clients(clients: dict[str, str], env_file: Path, command: list[str]) -> dict[str, Any]:
    """Check client capabilities and conflicts before setup saves credentials."""
    state_path = install_state_file()
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    clients = managed_clients(clients) | clients
    sources = _skill_sources()
    writes: dict[Path, str] = {}
    registrations: list[tuple[str, str, Path, dict[str, Any] | None, Any]] = []
    for client, executable in clients.items():
        if client not in CLIENTS:
            raise ValueError('Unknown client: ' + client)
        config = _config(client)
        if config.is_symlink():
            raise ValueError(f'Client config is a symlink; configure it manually: {config}')
        data = _read_config(config)
        key = {'claude-code': 'mcpServers', 'codex': 'mcp_servers', 'opencode': 'mcp'}[client]
        entries = data.get(key, {})
        if not isinstance(entries, dict):
            raise ValueError(f'Invalid MCP configuration: {config}')
        for name, entry in entries.items():
            if name != 'mlspace' and ('mlspace' in name.lower() or 'mlspace-plugin' in json.dumps(entry)):
                raise ValueError(f'Existing MLSpace integration {name} in {config}; migrate it first.')
        if client != 'opencode':
            if 'mlspace' in entries:
                raise ValueError(f'Existing direct MLSpace connection in {config}; '
                                 'remove it before installing the native plugin.')
            inspect_native(client, executable)
            registrations.append((client, executable, config, None, None))
            continue
        entry = {'type': 'local', 'command': command,
                 'environment': {'MLSPACE_ENV_FILE': str(env_file.absolute())}, 'enabled': True}
        current = entries.get('mlspace')
        previous = state.get('clients', {}).get(client, {}).get('entry_hash')
        if current is not None:
            comparable = dict(current)
            comparable.pop('type', None) if client != 'opencode' else None
            if comparable != entry and _hash(json.dumps(current, sort_keys=True)) != previous:
                raise ValueError(f'Existing mlspace entry differs in {config}; it was not overwritten.')
        registrations.append((client, executable, config, entry, current))
        skills_root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'opencode/skills'
        for name, content in sources.items():
            target = skills_root / name / 'SKILL.md'
            if target.is_symlink() or target.parent.is_symlink():
                if target.is_file() and target.read_text() == content:
                    continue
                raise ValueError(f'Existing skill symlink differs: {target}')
            if target.exists() and target.read_text() != content:
                if state.get('skills', {}).get(str(target)) != _hash(target.read_text()):
                    raise ValueError(f'Existing skill has local changes: {target}')
            writes[target] = content
    return {'state_path': state_path, 'state': state, 'writes': writes,
            'registrations': registrations}


def install_clients(clients: dict[str, str], env_file: Path, command: list[str]) -> list[str]:
    # Revalidate after human input: files may have changed since the preflight.
    plan = prepare_clients(clients, env_file, command)
    state, state_path = plan['state'], plan['state_path']
    retry = ['uvx', 'mlspace-plugin@latest', 'setup', '--force']
    for client, executable, *_ in plan['registrations']:
        retry.extend(['--client-path', f'{client}={executable}'])
    retry_hint = 'Retry: ' + shlex.join(retry)
    installed = []
    for client, executable, config, entry, _current in plan['registrations']:
        try:
            if client == 'opencode':
                text = config.read_text() if config.exists() else '{}\n'
                updated = set_jsonc_member(text, ['mcp', 'mlspace'], entry)
                if updated != text:
                    atomic_write(config, updated)
                saved = _read_config(config).get('mcp', {}).get('mlspace')
                if saved != entry:
                    raise ValueError(f'Client registration could not be confirmed for {client}; retry setup.')
                record: dict[str, Any] = {'mode': 'direct', 'version': __version__,
                          'entry_hash': _hash(json.dumps(saved, sort_keys=True))}
            else:
                status = install_native(client, executable, __version__)
                record = {'mode': 'native', 'version': status.version,
                          'marketplace_source': status.marketplace_source}
            state.setdefault('clients', {})[client] = record
            state.setdefault('configs', {})[client] = str(config.absolute())
            state.setdefault('executables', {})[client] = executable
            atomic_write(state_path, json.dumps(state, indent=2))
            installed.append(client)
        except (ValueError, OSError) as exc:
            raise ValueError(f'Could not register {client}. Already registered: '
                             f'{", ".join(installed) or "none"}. {exc}\n{retry_hint}') from exc
        except KeyboardInterrupt:
            print(f'Client setup interrupted. Already registered: {", ".join(installed) or "none"}.\n'
                  + retry_hint, file=sys.stderr)
            raise
    try:
        for target, content in plan['writes'].items():
            if not target.exists() or target.read_text() != content:
                atomic_write(target, content, 0o644)
            state.setdefault('skills', {})[str(target)] = _hash(content)
            atomic_write(state_path, json.dumps(state, indent=2))
    except (OSError, ValueError) as exc:
        raise ValueError(f'MCP registered: {", ".join(installed)}. Skill installation incomplete; '
                         'check permissions in the skills directory and rerun setup --force. '
                         'Verified credentials remain saved.') from exc
    return installed
