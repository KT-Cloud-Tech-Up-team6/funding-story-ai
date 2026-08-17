from decimal import Decimal

import pytest

from funding_story_ai.pricing import ModelPrice, PricingCatalog, TokenUsage
from funding_story_ai.usage import BudgetExceededError, UsageLedger


def test_budget_guard_fails_before_limit(tmp_path) -> None:
    pricing = PricingCatalog(
        {"test-model": ModelPrice(Decimal("1000000"), Decimal("0"), "test")}
    )
    ledger = UsageLedger(tmp_path / "usage.jsonl", Decimal("100"), Decimal("1"), pricing)
    with pytest.raises(BudgetExceededError):
        ledger.assert_can_spend("test-model", TokenUsage(prompt_tokens=100))


def test_ledger_sums_records(tmp_path) -> None:
    pricing = PricingCatalog({"test-model": ModelPrice(Decimal("1"), Decimal("1"), "test")})
    ledger = UsageLedger(tmp_path / "usage.jsonl", Decimal("100"), Decimal("1000"), pricing)
    record = ledger.build_record(
        request_id="r1",
        attempt=1,
        model="test-model",
        status="success",
        duration_ms=1,
        usage=TokenUsage(prompt_tokens=1000),
    )
    ledger.append(record)
    assert ledger.total_estimated_krw() == Decimal("1.000")
