from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _positive_decimal(name: str, default: str) -> Decimal:
    value = Decimal(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    project_id: str
    location: str = "global"
    primary_model: str = "gemini-3.7-flash"
    fallback_model: str = "gemini-3.6-flash"
    primary_access_attempts: int = 5
    max_output_tokens: int = 8192
    thinking_level: str = "LOW"
    spend_limit_krw: Decimal = Decimal("10000")
    usd_to_krw: Decimal = Decimal("1500")
    usage_ledger_path: Path = Path("reports/usage.jsonl")

    @classmethod
    def from_env(cls, *, require_project: bool = True) -> RuntimeSettings:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        if require_project and not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required")

        thinking_level = os.getenv("GEMINI_THINKING_LEVEL", "LOW").upper()
        if thinking_level not in {"MINIMAL", "LOW", "MEDIUM", "HIGH"}:
            raise ValueError("GEMINI_THINKING_LEVEL must be MINIMAL, LOW, MEDIUM, or HIGH")

        return cls(
            project_id=project_id,
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
            primary_model=os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.7-flash"),
            fallback_model=os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash"),
            primary_access_attempts=_positive_int("GEMINI_PRIMARY_ACCESS_ATTEMPTS", 5),
            max_output_tokens=_positive_int("GEMINI_MAX_OUTPUT_TOKENS", 8192),
            thinking_level=thinking_level,
            spend_limit_krw=_positive_decimal("GCP_SPEND_LIMIT_KRW", "10000"),
            usd_to_krw=_positive_decimal("USD_TO_KRW", "1500"),
            usage_ledger_path=Path(os.getenv("USAGE_LEDGER_PATH", "reports/usage.jsonl")),
        )
