from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .pricing import PricingCatalog, TokenUsage


class BudgetExceededError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UsageRecord:
    request_id: str
    attempt: int
    model: str
    status: str
    duration_ms: int
    usage: TokenUsage
    estimated_cost_usd: Decimal
    estimated_cost_krw: Decimal
    usd_to_krw: Decimal
    pricing_source: str
    finish_reason: str | None = None
    error_type: str | None = None
    created_at: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["estimated_cost_usd"] = str(self.estimated_cost_usd)
        value["estimated_cost_krw"] = str(self.estimated_cost_krw)
        value["usd_to_krw"] = str(self.usd_to_krw)
        value["created_at"] = self.created_at or datetime.now(UTC).isoformat()
        return value


class UsageLedger:
    def __init__(
        self,
        path: Path,
        spend_limit_krw: Decimal,
        usd_to_krw: Decimal,
        pricing: PricingCatalog,
    ) -> None:
        self.path = path
        self.spend_limit_krw = spend_limit_krw
        self.usd_to_krw = usd_to_krw
        self.pricing = pricing

    def total_estimated_krw(self) -> Decimal:
        if not self.path.exists():
            return Decimal("0")
        total = Decimal("0")
        with self.path.open(encoding="utf-8") as ledger_file:
            for line in ledger_file:
                if line.strip():
                    total += Decimal(str(json.loads(line)["estimated_cost_krw"]))
        return total

    def projected_cost_krw(self, model: str, usage: TokenUsage) -> Decimal:
        return self.pricing.get(model).estimate_usd(usage) * self.usd_to_krw

    def assert_can_spend(self, model: str, projected_usage: TokenUsage) -> Decimal:
        projected = self.projected_cost_krw(model, projected_usage)
        spent = self.total_estimated_krw()
        if spent + projected >= self.spend_limit_krw:
            raise BudgetExceededError(
                "Projected model cost would reach or exceed the configured GCP spend limit: "
                f"spent={spent}, projected={projected}, limit={self.spend_limit_krw} KRW"
            )
        return projected

    def build_record(
        self,
        *,
        request_id: str,
        attempt: int,
        model: str,
        status: str,
        duration_ms: int,
        usage: TokenUsage,
        finish_reason: str | None = None,
        error_type: str | None = None,
    ) -> UsageRecord:
        price = self.pricing.get(model)
        usd = price.estimate_usd(usage)
        return UsageRecord(
            request_id=request_id,
            attempt=attempt,
            model=model,
            status=status,
            duration_ms=duration_ms,
            usage=usage,
            estimated_cost_usd=usd,
            estimated_cost_krw=usd * self.usd_to_krw,
            usd_to_krw=self.usd_to_krw,
            pricing_source=price.source,
            finish_reason=finish_reason,
            error_type=error_type,
        )

    def append(self, record: UsageRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as ledger_file:
            ledger_file.write(json.dumps(record.to_json_dict(), ensure_ascii=False) + "\n")
