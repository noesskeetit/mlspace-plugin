"""Explicit choices and recoverable backups for existing OpenCode files."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .setup_ui import display

Resolutions = dict[str, tuple[str, str]]


def fingerprint(path: Path) -> str:
    """Include supporting skill files; never follow symlinks while inspecting them."""
    rows = []
    paths = [path, *sorted(path.rglob('*'))] if path.is_dir() and not path.is_symlink() else [path]
    for item in paths:
        name = str(item.relative_to(path))
        if item.is_symlink():
            value = 'link:' + str(item.readlink())
        elif item.is_file():
            value = hashlib.sha256(item.read_bytes()).hexdigest()
        elif item.is_dir():
            value = 'directory'
        else:
            raise ValueError(f'Unsupported or missing setup file: {item}')
        rows.append((name, value))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


@dataclass(frozen=True)
class Conflict:
    path: Path
    kind: str
    fingerprint: str

    @property
    def source(self) -> Path:
        return self.path.parent if self.kind == 'skill' else self.path

    def verify_unchanged(self) -> None:
        if fingerprint(self.source) != self.fingerprint:
            raise ValueError(f'File changed after your choice; run setup again: {self.path}')

    @classmethod
    def inspect(cls, path: Path, kind: str) -> Conflict:
        source = path.parent if kind == 'skill' else path
        return cls(path, kind, fingerprint(source))


def conflict_message(conflicts: list[Conflict]) -> str:
    lines = ['Existing MLSpace files differ; nothing was overwritten:']
    lines.extend(f'  {item.kind}: {item.path}' for item in conflicts)
    lines.append('Run setup in your terminal to keep custom skills or back up and replace conflicting files. '
                 '--force does not approve replacing them.')
    return '\n'.join(lines)


def choose_resolutions(conflicts: list[Conflict], *, non_interactive: bool) -> Resolutions:
    if not conflicts:
        return {}
    if non_interactive:
        raise ValueError(conflict_message(conflicts))
    for line in conflict_message(conflicts).splitlines():
        print(display(line), file=sys.stderr)
    print('Replacement saves a backup outside the skills directory. '
          'Other connections and additional user skills are preserved.', file=sys.stderr)
    choices = {}
    for item in conflicts:
        print(display(str(item.path)), file=sys.stderr)
        prompt = ('[k] Keep my skill (exclude from plugin updates), [r] Back up and replace, '
                  '[Enter] Cancel: ' if item.kind == 'skill' else
                  '[r] Back up config and replace only mcp.mlspace, [Enter] Cancel: ')
        while True:
            choice = input(prompt).strip().lower()
            if not choice:
                raise ValueError('Setup cancelled; no conflicting files were changed.')
            if choice == 'r' or (choice == 'k' and item.kind == 'skill'):
                choices[str(item.path)] = ('keep' if choice == 'k' else 'replace', item.fingerprint)
                break
            print('Choose one of the displayed options or press Enter to cancel.', file=sys.stderr)
    return choices


def backup_replacements(conflicts: list[Conflict], root: Path) -> Path | None:
    if not conflicts:
        return None
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix='setup-', dir=root))
    print(f'Backup directory: {display(str(backup))}', file=sys.stderr)
    for item in conflicts:
        item.verify_unchanged()
        destination = backup / 'skills' / item.path.parent.name if item.kind == 'skill' else backup / item.path.name
        if item.kind == 'skill':
            shutil.copytree(item.source, destination, symlinks=True)
        else:
            shutil.copy2(item.source, destination)
            destination.chmod(0o600)
        if fingerprint(destination) != item.fingerprint or fingerprint(item.source) != item.fingerprint:
            raise ValueError(f'File changed during backup; originals were not replaced: {item.path}')
    return backup
