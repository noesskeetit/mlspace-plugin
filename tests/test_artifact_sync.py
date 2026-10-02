"""Guard against openapi -> body_schemas.json drift.

Regenerate the artifact in-memory via the generator's own logic and assert it is
byte-identical to the committed src/mlspace_mcp/spec/body_schemas.json. If this
fails, someone changed the bundled OpenAPI spec (or the generator) without
re-running `python scripts/gen_body_schemas.py`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_GEN = _ROOT / "scripts" / "gen_body_schemas.py"
_ARTIFACT = _ROOT / "src" / "mlspace_mcp" / "spec" / "body_schemas.json"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_body_schemas", _GEN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_artifact_in_sync_with_openapi():
    gen = _load_generator()
    regenerated = gen.render(gen.build())
    committed = _ARTIFACT.read_text()
    assert regenerated == committed, (
        "body_schemas.json is stale: re-run "
        "`python scripts/gen_body_schemas.py`"
    )
