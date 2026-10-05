"""Terminal onboarding shared by humans and explicitly configured automation."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import USER_AGENT
from .client_setup import (
    CLIENTS,
    atomic_write,
    detect_clients,
    install_clients,
    install_state_file,
    managed_clients,
    prepare_clients,
    server_command,
)
from .config import (
    DEFAULT_BASE_URL,
    LITERAL_DOTENV_MARKER,
    credential_files,
    credential_pointer_file,
    read_dotenv_file,
    user_config_file,
)
from .setup_conflicts import Resolutions, choose_resolutions
from .setup_ui import choose_workspaces, display, masked_prompt
from .setup_verification import verify_client
from .tls import safe_error as _safe_error
from .tls import tls_context

HEADER = f'# MLSpace credentials, written by mlspace-plugin setup.\n{LITERAL_DOTENV_MARKER}\n'


def _ask(label: str, secret: bool = True, hidden: bool = True) -> str:
    while True:
        value = masked_prompt(f'  {label}: ') if hidden else input(f'  {label}: ')
        if re.match(r'^\s*(?:export\s+)?MLSPACE_\w+\s*=', value):
            print('Enter only the value, without MLSPACE_...= or export.', file=sys.stderr)
        elif value.strip():
            return value if secret else value.strip()
        else:
            print('Required. Paste the value; asterisks show that it was entered.', file=sys.stderr)


def _resolve_base_url(target: Path, override: str | None) -> str:
    saved = read_dotenv_file(target) if target.is_file() else {}
    return ((override or '').strip() or os.environ.get('MLSPACE_BASE_URL', '').strip()
            or str(saved.get('MLSPACE_BASE_URL') or DEFAULT_BASE_URL)).rstrip('/')


def _fetch_workspaces(key_id: str, key_secret: str, *, base_url: str,
                      ca_file: str = '') -> list[dict[str, str]]:
    from .auth import TokenManager
    from .client import MLSpaceClient

    async def fetch() -> Any:
        async with httpx.AsyncClient(
            timeout=30, verify=tls_context(ca_file), headers={"User-Agent": USER_AGENT},
        ) as http:
            tokens = TokenManager(http, base_url=base_url, client_id=key_id, client_secret=key_secret)
            client = MLSpaceClient(http, tokens, base_url=base_url, api_key='', workspace_id='')
            return await client.request('GET', '/public/v2/workspaces/v3/')

    response = asyncio.run(fetch())
    spaces = response.get('workspaces') if isinstance(response, dict) else None
    if not isinstance(spaces, list) or not spaces:
        raise ValueError('No workspaces visible to these access keys.')
    catalogue = []
    seen = set()
    for row in spaces:
        if not isinstance(row, dict) or not (key := row.get('id') or row.get('workspace_id')):
            raise ValueError('Workspace API returned an entry without an ID.')
        if str(key) in seen:
            raise ValueError('Workspace API returned duplicate IDs.')
        seen.add(str(key))
        catalogue.append({'id': str(key), 'name': str(row.get('name') or key),
                          'project_name': str(row.get('project_name') or '')})
    return sorted(catalogue, key=lambda r: (r['name'].casefold(), r['project_name'], r['id']))
def _write(path: Path, values: dict[str, str]) -> None:
    """Atomically replace ``path`` with a 0600 dotenv file."""
    if path.is_symlink():
        raise ValueError("Credentials target must not be a symlink.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent == user_config_file().parent:
        path.parent.chmod(0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            body = "".join(
                f"MLSPACE_{name}={json.dumps(value, ensure_ascii=False)}\n"
                for name, value in values.items()
            )
            fh.write(HEADER + body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def save_credential_pointer(env_file: Path) -> None:
    pointer = credential_pointer_file()
    pointer.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    pointer.parent.chmod(0o700)
    atomic_write(pointer, json.dumps({'env_file': str(env_file.absolute())}) + '\n')


def _verify(values: dict[str, str], *, base_url: str) -> str | None:
    """Check selected workspace details and IDs. Returns a safe error, or None.

    The caller preserves the previous file if any selected workspace fails.
    """
    import asyncio

    import httpx
    from pydantic import SecretStr

    from .auth import TokenManager
    from .config import Settings
    from .workspace_context import WorkspaceClients

    async def run() -> str | None:
        try:
            # Explicit values keep old environment selectors out of this check.
            settings = Settings(  # type: ignore[call-arg]
                _env_file=None,
                base_url=base_url,
                client_id=values["CLIENT_ID"],
                client_secret=SecretStr(values["CLIENT_SECRET"]),
                api_key=SecretStr(values.get("API_KEY", "")),
                workspace_id=values.get("WORKSPACE_ID", ""),
                workspaces=json.loads(values.get("WORKSPACES", "[]")),
                namespace="",
            )
            async with httpx.AsyncClient(
                timeout=30, verify=tls_context(values.get("CA_FILE", "")),
                headers={"User-Agent": USER_AGENT},
            ) as http:
                tokens = TokenManager(
                    http, base_url=base_url, client_id=values["CLIENT_ID"],
                    client_secret=values["CLIENT_SECRET"],
                )
                clients = WorkspaceClients(settings, http, tokens)
                verified = 0
                errors = []
                for selection in clients.selected:
                    try:
                        client = await clients.resolve(selection.id)
                        data = await client.request(
                            "GET", "/public/v2/workspaces/v3/{workspace_id}",
                            path_params={"workspace_id": selection.id},
                        )
                        if not isinstance(data, dict) or data.get("id") != selection.id:
                            errors.append(f"{selection.id}: workspace identity was not confirmed")
                            continue
                        verified += 1
                    except Exception as exc:  # noqa: BLE001 — verify every selected workspace
                        errors.append(f"{selection.id}: {_safe_error(exc)}")
                print(
                    f"  checked: {verified}/{len(clients.selected)} selected workspace(s) verified "
                    "(workspace details and ID)",
                    file=sys.stderr,
                )
                return "; ".join(errors) or None
        except Exception as exc:  # noqa: BLE001 — report failures without exposing transport details
            return _safe_error(exc)

    return asyncio.run(run())



def _clients(requested: list[str], paths: list[str], non_interactive: bool) -> dict[str, str]:
    detected = detect_clients()
    explicit = {}
    for item in paths:
        name, separator, path = item.partition('=')
        executable = Path(path).expanduser().absolute()
        if not separator or name not in CLIENTS or not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError('Use --client-path CLIENT=/absolute/path/to/executable.')
        detected[name] = str(executable)
        explicit[name] = str(executable)
    managed = managed_clients(explicit)
    detected = managed | detected
    if requested:
        if any(name not in detected for name in requested):
            raise ValueError('Requested client not found. Install it or use --client-path CLIENT=/path.')
        return {name: detected[name] for name in requested}
    if explicit:
        return managed | explicit
    if managed:
        print('Updating all previously connected MLSpace clients: ' + ', '.join(managed), file=sys.stderr)
        return managed | explicit
    if not explicit and install_state_file().exists():
        raise ValueError('No previous MLSpace connections remain. Select a new connection explicitly '
                         'with --client or --client-path.')
    if len(detected) == 1:
        print('Client detected: ' + next(iter(detected)), file=sys.stderr)
        return detected
    if not detected:
        if non_interactive:
            raise ValueError('No coding client found; use --client-path or --config-only.')
        print('No Claude Code, Codex or OpenCode found. Enter CLIENT=/absolute/path, '
              'or press Enter to stop and install a client.', file=sys.stderr)
        custom = input('Client executable: ').strip()
        if custom:
            return _clients([], [custom], True)
        raise ValueError('Install Claude Code, Codex or OpenCode, then run setup again. '
                         'For other MCP clients use --config-only.')
    if non_interactive:
        raise ValueError('Multiple clients found; select with --client (repeat for several).')
    print('Choose clients: type to search, Space to select, Enter to continue.', file=sys.stderr)
    selected = choose_workspaces([{'id': name, 'name': name, 'project_name': path}
                                  for name, path in detected.items()])
    return {row['id']: detected[row['id']] for row in selected}


def run_init(path: Path | None = None, *, force: bool = False, verify: bool = True,
             base_url: str | None = None, config_only: bool = False,
             non_interactive: bool = False, from_env: bool = False,
             credentials_file: Path | None = None, workspace_ids: list[str] | None = None,
             clients: list[str] | None = None, client_paths: list[str] | None = None,
             ca_file: Path | None = None, replace_credentials: bool = False,
             list_workspaces: bool = False, search: str = '', offset: int = 0, limit: int = 20) -> int:
    try:
        return _run_init(path, force=force, verify=verify, base_url=base_url,
                         config_only=config_only, non_interactive=non_interactive,
                         from_env=from_env, credentials_file=credentials_file,
                         workspace_ids=workspace_ids or [], clients=clients or [],
                         client_paths=client_paths or [], ca_file=ca_file,
                         replace_credentials=replace_credentials, list_workspaces=list_workspaces,
                         search=search, offset=offset, limit=limit)
    except KeyboardInterrupt:
        print('\nSetup cancelled; previous credentials preserved unless saving already completed.', file=sys.stderr)
        return 130
    except EOFError:
        print('\nNo interactive input. Run `uvx mlspace-plugin@latest setup` yourself in a terminal (SSH works). '
              'Agents: use INSTALL_AGENT.md; never ask for keys in chat.', file=sys.stderr)
        return 1
    except (ValueError, OSError, httpx.HTTPError) as exc:
        # Only our own ValueErrors carry displayable text. Third-party errors may echo keys.
        message = str(exc) if type(exc) is ValueError else _safe_error(exc)
        print('Setup failed: ' + '\n'.join(display(line) for line in message.splitlines()), file=sys.stderr)
        return 1


def _run_init(path: Path | None, **options: Any) -> int:
    target = (path or credential_files()[0]).expanduser().absolute()
    listing = options['list_workspaces']
    non_interactive = options['non_interactive']
    if not non_interactive and not sys.stdin.isatty():
        raise EOFError
    if options['from_env'] and options['credentials_file']:
        raise ValueError('Choose either --from-env or --credentials-file.')
    if target.is_symlink():
        raise ValueError('Credentials target must not be a symlink.')
    if target.exists() and not target.is_file():
        raise ValueError('Credentials target must be a regular file.')
    if target.exists() and not options['force'] and not listing:
        raise ValueError('Configuration already exists. Use --force to reconfigure; saved keys will be reused.')
    if not options['verify'] and (not options['config_only'] or not options['workspace_ids']):
        raise ValueError('--no-verify requires --config-only and explicit --workspace IDs; result is unverified.')
    if options['offset'] < 0 or not 1 <= options['limit'] <= 100:
        raise ValueError('Use offset >= 0 and limit between 1 and 100.')
    saved = read_dotenv_file(target) if target.is_file() else {}
    endpoint = _resolve_base_url(target, options['base_url'])
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('API endpoint must be an HTTPS URL without credentials, query or fragment.')
    if os.environ.get('SSL_CERT_DIR'):
        raise ValueError('SSL_CERT_DIR cannot be carried into client startup. Unset it for setup and use '
                         '--ca-file /path/to/trusted-ca.pem or install the CA in the system trust store.')
    selected_clients = {} if options['config_only'] or listing else _clients(
        options['clients'], options['client_paths'], non_interactive)
    command = server_command() if selected_clients and 'opencode' in selected_clients | managed_clients(selected_clients) else []
    resolutions: Resolutions = {}
    if selected_clients:
        plan = prepare_clients(selected_clients, target, command, collect_conflicts=True)
        resolutions = choose_resolutions(plan.get('conflicts', []), non_interactive=non_interactive)
        print('MCP and skills will be kept together for: ' +
              ', '.join(row[0] for row in plan['registrations']), file=sys.stderr)
    if not listing:
        print('[1/4] Access keys. Paste values only; asterisks hide both fields. '
              'Keys stay in your user config, not in chat.', file=sys.stderr)
    if options['credentials_file']:
        source = read_dotenv_file(options['credentials_file'].expanduser())
    elif options['from_env']:
        source = dict(os.environ)
    elif not options['replace_credentials'] and str(saved.get('MLSPACE_BASE_URL') or DEFAULT_BASE_URL).rstrip('/') == endpoint:
        source = saved
    else:
        source = {}
    keys = {}
    for name, label in [('CLIENT_ID', 'Cloud.ru Key ID'), ('CLIENT_SECRET', 'Cloud.ru Key Secret')]:
        value = source.get('MLSPACE_' + name)
        if not value or not value.strip():
            if non_interactive or options['credentials_file'] or options['from_env']:
                raise ValueError('Missing credentials for this endpoint. Run setup in your terminal, '
                                 'or explicitly select --from-env / --credentials-file.')
            value = _ask(label, secret=name == 'CLIENT_SECRET')
        keys[name] = value
    ca = str(options['ca_file'] or saved.get('MLSPACE_CA_FILE') or os.environ.get('SSL_CERT_FILE') or '')
    ca = str(Path(ca).expanduser().absolute()) if ca else ''
    if not listing:
        print('[2/4] Checking TLS and loading workspaces…', file=sys.stderr)
    if options['verify'] or listing:
        while True:
            try:
                rows = _fetch_workspaces(keys['CLIENT_ID'], keys['CLIENT_SECRET'], base_url=endpoint, ca_file=ca)
                break
            except ValueError:
                raise
            except Exception as exc:
                error = _safe_error(exc)
                if not non_interactive and 'TLS certificate' in error:
                    print(error, file=sys.stderr)
                    ca = input('Trusted CA PEM path from your administrator (Enter to cancel): ').strip()
                    if not ca:
                        raise ValueError('TLS setup stopped; no credentials saved.') from None
                    ca = str(Path(ca).expanduser().absolute())
                    continue
                raise ValueError(error) from None
    else:
        rows = [{'id': key, 'name': key, 'project_name': ''} for key in dict.fromkeys(options['workspace_ids'])]
    if listing:
        terms = options['search'].casefold().split()
        matches = [row for row in rows if all(term in ' '.join(row.values()).casefold() for term in terms)]
        offset, limit = options['offset'], options['limit']
        print(json.dumps({'total': len(matches), 'offset': offset, 'limit': limit,
                          'has_more': offset + limit < len(matches), 'workspaces': matches[offset:offset+limit]}, ensure_ascii=False))
        return 0
    requested = options['workspace_ids']
    if requested:
        if set(requested) - {row['id'] for row in rows}:
            raise ValueError('Requested workspace IDs are not in the accessible workspace list.')
        selected = [row for row in rows if row['id'] in requested]
    elif non_interactive:
        raise ValueError('Select workspace IDs with --workspace. Use --list-workspaces --search to find them.')
    elif len(rows) == 1:
        selected = rows
    else:
        print('Find your workspaces: type a name, project or ID. Space selects; Enter finishes.', file=sys.stderr)
        old = json.loads(str(saved.get('MLSPACE_WORKSPACES') or '[]'))
        selected = choose_workspaces(rows, [row['id'] for row in old if isinstance(row, dict) and 'id' in row])
    values = {key.removeprefix('MLSPACE_'): value for key, value in saved.items()
              if key.startswith('MLSPACE_') and value is not None
              and key not in {'MLSPACE_API_KEY', 'MLSPACE_WORKSPACE_ID', 'MLSPACE_WORKSPACES', 'MLSPACE_NAMESPACE'}}
    values.update(keys)
    values.update(BASE_URL=endpoint, CA_FILE=ca,
                  WORKSPACES=json.dumps(selected, ensure_ascii=False, separators=(',', ':')))
    if len(selected) == 1:
        values['WORKSPACE_ID'] = selected[0]['id']
    print(f'[3/4] Verifying {len(selected)} selected workspace(s)…', file=sys.stderr)
    if options['verify']:
        problem = _verify(values, base_url=endpoint)
        if problem:
            raise ValueError(problem)
    if ca:
        # Persist the validated public CA independently of /tmp and shell environment.
        content = Path(ca).read_text(encoding='ascii')
        destination = target.parent / ('ca-' + hashlib.sha256(content.encode()).hexdigest()[:16] + '.pem')
        tls_context(ca)
        atomic_write(destination, content)
        values['CA_FILE'] = str(destination)
    try:
        _write(target, values)
    except (OSError, ValueError) as exc:
        raise ValueError(f'Could not save credentials to {target}. No clients were connected. '
                         'Check the target and its permissions, then rerun setup.') from exc
    print(f'Credentials saved: {target} (0600).', file=sys.stderr)
    try:
        save_credential_pointer(target)
    except (OSError, ValueError) as exc:
        raise ValueError(f'Credentials saved, but their locator could not be saved to {credential_pointer_file()}. '
                         'No clients were connected. Check permissions and rerun setup --force with the same --path.') from exc
    if selected_clients:
        print('[4/4] Connecting MCP and installing skills…', file=sys.stderr)
        try:
            install_clients(selected_clients, target, command, resolutions=resolutions)
            for client, executable, *_ in plan['registrations']:
                print(f'  {client}: installed; checking skills and MCP process…', file=sys.stderr)
                verify_client(client, executable, target, command)
                print(f'  {client}: packaged skills checked (kept user overrides excluded); MCP process verified.', file=sys.stderr)
        except (OSError, ValueError) as exc:
            reason = str(exc) if type(exc) is ValueError else _safe_error(exc)
            raise ValueError('Credentials saved; client setup is incomplete. ' + reason) from exc
    if not options['verify']:
        print('UNVERIFIED configuration saved by explicit request. No client was connected.', file=sys.stderr)
        return 0
    if selected_clients:
        print('Done. Open a new client session (restart it if MCP is not visible). '
              'The client starts the MCP server automatically.\n'
              'Loading into your next client session remains to be confirmed there.\n'
              'Try: «Покажи выбранные воркспейсы и запущенные задачи, ничего не меняй».', file=sys.stderr)
    else:
        print('API/TLS verified. Config-only setup complete; client integration was not requested.', file=sys.stderr)
    return 0
