from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .adapter import GeminiAdapter
from .config import RuntimeSettings

SMOKE_SCHEMA = {
    "type": "object",
    "properties": {"status": {"type": "string", "enum": ["ok"]}},
    "required": ["status"],
    "additionalProperties": False,
}


def build_runtime(*, require_project: bool = True) -> RuntimeSettings:
    load_dotenv(dotenv_path=Path(".env"), override=False)
    return RuntimeSettings.from_env(require_project=require_project)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini adapter smoke test")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Validate configuration only")
    mode.add_argument("--live", action="store_true", help="Run one real Vertex AI request")
    args = parser.parse_args()

    settings = build_runtime(require_project=args.live)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "mode": "dry-run",
                    "model": settings.primary_model,
                    "location": settings.location,
                    "configuration_valid": True,
                },
                ensure_ascii=False,
            )
        )
        return

    adapter = GeminiAdapter(settings)
    result = adapter.generate_json(
        prompt='Return a JSON object with status set to "ok".',
        response_schema=SMOKE_SCHEMA,
    )
    print(
        json.dumps(
            {
                "model": result.model,
                "data": result.data,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
