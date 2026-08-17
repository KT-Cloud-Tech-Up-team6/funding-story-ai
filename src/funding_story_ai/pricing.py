from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

MILLION = Decimal("1000000")


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cached_tokens: int = 0

    @property
    def billable_output_tokens(self) -> int:
        return self.output_tokens + self.thinking_tokens


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    source: str

    def estimate_usd(self, usage: TokenUsage) -> Decimal:
        input_cost = Decimal(usage.prompt_tokens) * self.input_usd_per_million / MILLION
        output_cost = (
            Decimal(usage.billable_output_tokens) * self.output_usd_per_million / MILLION
        )
        return input_cost + output_cost


class PricingCatalog:
    """Explicit model prices used for estimates and the preflight budget guard."""

    _GEMINI_36_STANDARD = ModelPrice(
        input_usd_per_million=Decimal("1.50"),
        output_usd_per_million=Decimal("7.50"),
        source="google-standard-pricing-2026-08-14",
    )

    def __init__(self, prices: dict[str, ModelPrice] | None = None) -> None:
        self._prices = prices or self._prices_from_env()

    @classmethod
    def _prices_from_env(cls) -> dict[str, ModelPrice]:
        input_37 = os.getenv("GEMINI_37_INPUT_USD_PER_MILLION")
        output_37 = os.getenv("GEMINI_37_OUTPUT_USD_PER_MILLION")
        if bool(input_37) != bool(output_37):
            raise ValueError("Both Gemini 3.7 price environment variables must be set together")

        price_37 = (
            ModelPrice(
                input_usd_per_million=Decimal(input_37),
                output_usd_per_million=Decimal(output_37),
                source="configured-gemini-3.7-price",
            )
            if input_37 and output_37
            else ModelPrice(
                input_usd_per_million=cls._GEMINI_36_STANDARD.input_usd_per_million,
                output_usd_per_million=cls._GEMINI_36_STANDARD.output_usd_per_million,
                source="conservative-proxy:gemini-3.6-flash-standard-2026-08-14",
            )
        )
        return {
            "gemini-3.7-flash": price_37,
            "gemini-3.6-flash": cls._GEMINI_36_STANDARD,
        }

    def get(self, model: str) -> ModelPrice:
        try:
            return self._prices[model]
        except KeyError as exc:
            raise ValueError(f"No price configured for model: {model}") from exc
