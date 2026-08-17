from decimal import Decimal

from funding_story_ai.pricing import ModelPrice, PricingCatalog, TokenUsage


def test_price_includes_thinking_tokens() -> None:
    price = ModelPrice(Decimal("1"), Decimal("2"), "test")
    usage = TokenUsage(prompt_tokens=1_000_000, output_tokens=250_000, thinking_tokens=250_000)
    assert price.estimate_usd(usage) == Decimal("2")


def test_37_uses_conservative_proxy_without_config(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_37_INPUT_USD_PER_MILLION", raising=False)
    monkeypatch.delenv("GEMINI_37_OUTPUT_USD_PER_MILLION", raising=False)
    price = PricingCatalog().get("gemini-3.7-flash")
    assert price.input_usd_per_million == Decimal("1.50")
    assert price.output_usd_per_million == Decimal("7.50")
    assert price.source.startswith("conservative-proxy")
