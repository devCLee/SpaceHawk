"""Export the OpenAPI document so the web tier's TS client can be regenerated.

Writes ``packages/shared-types/openapi.json`` (the contract consumed by
``openapi-typescript``). Run via ``export-openapi`` (see pyproject scripts) or
``python -m orbital_engine.openapi``.
"""

from __future__ import annotations

import json
from pathlib import Path

from orbital_engine.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT = REPO_ROOT / "packages" / "shared-types" / "openapi.json"


def main() -> None:
    app = create_app()
    schema = app.openapi()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"[export-openapi] wrote {OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
