from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from .adapter import GeminiAdapter
from .data_repository import DataRepository
from .pipeline import StoryPipeline
from .pricing import PricingCatalog, TokenUsage
from .prompting import build_story_prompt
from .selector import TemplateSelector
from .smoke import build_runtime


def _default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("artifacts/generations") / f"story-{timestamp}.json"


def build_dry_run_summary(
    repository: DataRepository,
    brief_name: str | None,
    template_id: str | None,
    brief_path: Path | None = None,
    category_profile_id: str | None = None,
) -> dict:
    load_dotenv(dotenv_path=Path(".env"), override=False)
    settings, ledger = build_runtime(require_project=False)
    brief = _load_brief(repository, brief_name=brief_name, brief_path=brief_path)
    if template_id:
        template = repository.get_template(template_id)
        selection_scores = {template_id: 0}
        selection_reasons = ["explicit template request"]
    else:
        profile = (
            repository.get_category_profile(category_profile_id)
            if category_profile_id
            else None
        )
        selection = TemplateSelector().select(
            brief,
            repository.load_templates(),
            soft_boosts=(
                profile["template_soft_boosts"] if profile is not None else None
            ),
        )
        template = repository.get_template(selection.template_id)
        selection_scores = selection.scores
        selection_reasons = list(selection.reasons)
    prompt = build_story_prompt(brief=brief, template=template)
    projected_usage = TokenUsage(
        prompt_tokens=max(1, len(prompt.encode("utf-8"))),
        output_tokens=settings.max_output_tokens,
    )
    projected_call_krw = ledger.assert_can_spend(
        settings.primary_model, projected_usage
    )
    price = PricingCatalog().get(settings.primary_model)
    return {
        "mode": "dry-run",
        "brief_id": brief["brief_id"],
        "template_id": template["id"],
        "template_version": repository.get_template_version(template["id"]),
        "selection_scores": selection_scores,
        "selection_reasons": selection_reasons,
        "category_profile_id": category_profile_id,
        "model": settings.primary_model,
        "prompt_utf8_bytes": len(prompt.encode("utf-8")),
        "max_output_tokens": settings.max_output_tokens,
        "projected_single_call_cost_krw": str(projected_call_krw),
        "projected_two_call_upper_proxy_krw": str(projected_call_krw * 3),
        "projection_note": (
            "두 번째 수정 프롬프트가 첫 프롬프트보다 커질 수 있어 단일 호출 추정치의 "
            "3배를 보수적 대리값으로 표시"
        ),
        "pricing_source": price.source,
        "spent_estimated_krw": str(ledger.total_estimated_krw()),
        "spend_limit_krw": str(settings.spend_limit_krw),
    }


def _load_brief(
    repository: DataRepository,
    *,
    brief_name: str | None,
    brief_path: Path | None,
) -> dict:
    if brief_path is not None:
        return repository.load_brief_path(brief_path)
    return repository.load_brief(brief_name or "robot-vacuum/brief.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a structured crowdfunding story")
    brief_source = parser.add_mutually_exclusive_group()
    brief_source.add_argument(
        "--brief",
        help="File name under examples (default: robot-vacuum/brief.json)",
    )
    brief_source.add_argument(
        "--brief-path",
        type=Path,
        help="Path to a schema-validated story brief",
    )
    parser.add_argument("--template", help="Explicit template id; omit for selection")
    parser.add_argument(
        "--category-profile",
        help="Optional category profile id for examples and template soft boosts",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Validate and estimate only")
    mode.add_argument("--live", action="store_true", help="Call Vertex AI and save JSON")
    parser.add_argument("--output", type=Path, help="New output path for --live")
    args = parser.parse_args()

    repository = DataRepository()
    if args.dry_run:
        print(
            json.dumps(
                build_dry_run_summary(
                    repository,
                    args.brief,
                    args.template,
                    brief_path=args.brief_path,
                    category_profile_id=args.category_profile,
                ),
                ensure_ascii=False,
            )
        )
        return

    load_dotenv(dotenv_path=Path(".env"), override=False)
    settings, ledger = build_runtime()
    adapter = GeminiAdapter(settings, ledger)
    pipeline = StoryPipeline(repository=repository, adapter=adapter)
    result = pipeline.invoke(
        _load_brief(
            repository,
            brief_name=args.brief,
            brief_path=args.brief_path,
        ),
        template_id=args.template,
        category_profile_id=args.category_profile,
    )
    output_path = args.output or _default_output_path()
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output_path),
                "request_id": result["request_id"],
                "model": result["model"],
                "template_id": result["template_id"],
                "review_required": result["review_required"],
                "warning_count": len(result["warnings"]),
                "usage": result["usage"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
