from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .adapter import GeminiAdapter
from .config import RuntimeSettings
from .pricing import PricingCatalog, TokenUsage
from .usage import UsageLedger

SMOKE_SCHEMA = {
    "type": "object",
    "properties": {"status": {"type": "string", "enum": ["ok"]}},
    "required": ["status"],
    "additionalProperties": False,
}


def build_runtime(*, require_project: bool = True) -> tuple[RuntimeSettings, UsageLedger]:
    load_dotenv(dotenv_path=Path(".env"), override=False)
    settings = RuntimeSettings.from_env(require_project=require_project)
    pricing = PricingCatalog()
    ledger = UsageLedger(
        path=settings.usage_ledger_path,
        spend_limit_krw=settings.spend_limit_krw,
        usd_to_krw=settings.usd_to_krw,
        pricing=pricing,
    )
    return settings, ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini adapter smoke test")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Estimate without an API request")
    mode.add_argument("--live", action="store_true", help="Run one real Vertex AI request")
    args = parser.parse_args()

    settings, ledger = build_runtime(require_project=args.live)
    if args.dry_run:
        projected = ledger.assert_can_spend(
            settings.primary_model,
            TokenUsage(prompt_tokens=64, output_tokens=settings.max_output_tokens),
        )
        print(
            json.dumps(
                {
                    "mode": "dry-run",
                    "model": settings.primary_model,
                    "projected_cost_krw": str(projected),
                    "spent_estimated_krw": str(ledger.total_estimated_krw()),
                    "spend_limit_krw": str(settings.spend_limit_krw),
                    "ledger": str(Path(settings.usage_ledger_path)),
                },
                ensure_ascii=False,
            )
        )
        return

    adapter = GeminiAdapter(settings, ledger)
    result = adapter.generate_json(
        prompt='Return a JSON object with status set to "ok".',
        response_schema=SMOKE_SCHEMA,
    )
    print(
        json.dumps(
            {
                "request_id": result.request_id,
                "model": result.model,
                "data": result.data,
                "usage": {
                    "prompt_tokens": result.usage.prompt_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "thinking_tokens": result.usage.thinking_tokens,
                },
                "duration_ms": result.duration_ms,
                "attempts": result.attempts,
                "finish_reason": result.finish_reason,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
