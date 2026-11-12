"""Regenerate docs/openapi.json from the API schemas (the published contract).

uv run python scripts/export_openapi.py
"""

import json

from banana_english.api.app import create_app
from banana_english.config.container import build_container
from banana_english.config.settings import PROJECT_ROOT, Settings

app = create_app(build_container(Settings(database_url="sqlite://")))
out = PROJECT_ROOT / "docs/openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {out}")
