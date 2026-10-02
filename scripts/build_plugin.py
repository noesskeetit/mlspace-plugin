"""Build a marketplace archive with skills and a version-pinned PyPI runtime.

Usage: python scripts/build_plugin.py --output dist/plugins
The server and its dependencies are downloaded from PyPI on first launch.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from gen_plugin import ROOT, __version__, build, build_marketplaces


def build_release(output: Path) -> tuple[Path, Path]:
    output = output.resolve()
    destination = output / f"mlspace-plugin-{__version__}"
    archive = output / f"{destination.name}.zip"
    if destination.exists() or archive.exists():
        raise FileExistsError(f"Release already exists: {destination}")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mlspace-build-", dir=output) as stage:
        root = Path(stage) / destination.name
        plugin = root / "plugin"
        for name, content in build().items():
            target = plugin / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        shutil.copytree(ROOT / "plugin/skills", plugin / "skills",
                        ignore=shutil.ignore_patterns(".*", "__pycache__"))
        for target in (root / "README.md", plugin / "README.md"):
            shutil.copyfile(ROOT / "plugin/README.md", target)
        shutil.copyfile(ROOT / "LICENSE", plugin / "LICENSE")
        for name, content in build_marketplaces().items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        hashes = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                hashes.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}")
        (root / "SHA256SUMS").write_text("\n".join(hashes) + "\n", encoding="utf-8")
        staged_archive = Path(stage) / archive.name
        with ZipFile(staged_archive, "w", compression=ZIP_DEFLATED) as zipped:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zipped.write(path, f"{root.name}/{path.relative_to(root).as_posix()}")
        root.rename(destination)
        staged_archive.rename(archive)
    return destination, archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/plugins")
    args = parser.parse_args()
    root, archive = build_release(args.output)
    print(f"Plugin marketplace: {root}\nArchive: {archive}")


if __name__ == "__main__":
    main()
