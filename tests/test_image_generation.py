import base64
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from funding_story_ai.image_generation import (
    ImageSettings,
    ImageUsageLedger,
    OpenAIImageAdapter,
    OpenAIImageBudgetExceeded,
)


class FakeImages:
    def __init__(self) -> None:
        self.kwargs = None

    def edit(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(b"fake-image").decode(),
                    revised_prompt=None,
                )
            ],
            usage=SimpleNamespace(
                input_tokens_details=SimpleNamespace(text_tokens=10, image_tokens=20),
                output_tokens=30,
            ),
        )

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(b"generated-image").decode(),
                    revised_prompt=None,
                )
            ],
            usage=SimpleNamespace(
                input_tokens_details=SimpleNamespace(text_tokens=12, image_tokens=0),
                output_tokens=30,
            ),
        )


def test_image_adapter_tracks_usage_and_omits_input_fidelity(tmp_path) -> None:
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"reference")
    settings = ImageSettings(
        spend_limit_usd=Decimal("10.00"),
        reserve_usd_per_call=Decimal("0.50"),
        ledger_path=tmp_path / "image-usage.jsonl",
    )
    ledger = ImageUsageLedger(settings.ledger_path, settings.spend_limit_usd)
    images = FakeImages()
    adapter = OpenAIImageAdapter(
        settings,
        ledger,
        client=SimpleNamespace(images=images),
    )

    result = adapter.edit_reference(
        section_id="hero", reference_path=reference, prompt="제품 히어로 이미지"
    )

    assert result.image_bytes == b"fake-image"
    assert result.estimated_cost_usd == Decimal("0.00111")
    assert "input_fidelity" not in images.kwargs
    assert ledger.total_estimated_usd() == Decimal("0.00111")


def test_image_budget_guard_reserves_before_call(tmp_path) -> None:
    ledger_path = tmp_path / "image-usage.jsonl"
    ledger_path.write_text('{"estimated_cost_usd":"9.75"}\n', encoding="utf-8")
    ledger = ImageUsageLedger(ledger_path, Decimal("10.00"))
    with pytest.raises(OpenAIImageBudgetExceeded):
        ledger.assert_can_call(Decimal("0.50"))


def test_image_adapter_generates_without_reference_image(tmp_path) -> None:
    settings = ImageSettings(
        spend_limit_usd=Decimal("10.00"),
        reserve_usd_per_call=Decimal("0.50"),
        ledger_path=tmp_path / "image-usage.jsonl",
    )
    ledger = ImageUsageLedger(settings.ledger_path, settings.spend_limit_usd)
    images = FakeImages()
    adapter = OpenAIImageAdapter(
        settings,
        ledger,
        client=SimpleNamespace(images=images),
    )

    result = adapter.generate_text(section_id="hero", prompt="가상 제품 이미지")

    assert result.image_bytes == b"generated-image"
    assert result.usage.image_input_tokens == 0
    assert "image" not in images.kwargs
    assert json.loads(settings.ledger_path.read_text())["input_mode"] == "text-generate"
