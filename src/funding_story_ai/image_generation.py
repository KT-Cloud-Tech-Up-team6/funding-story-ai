from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from openai import OpenAI

MILLION = Decimal("1000000")


class OpenAIImageBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ImageSettings:
    model: str = "gpt-image-2"
    size: str = "1536x1024"
    quality: str = "low"
    output_format: str = "jpeg"
    output_compression: int = 85
    spend_limit_usd: Decimal = Decimal("5.00")
    reserve_usd_per_call: Decimal = Decimal("0.50")
    ledger_path: Path = Path("reports/openai-image-usage.jsonl")

    @classmethod
    def from_env(cls) -> ImageSettings:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise ValueError("OPENAI_API_KEY is required")
        return cls(
            model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
            size=os.getenv("OPENAI_IMAGE_SIZE", "1536x1024"),
            quality=os.getenv("OPENAI_IMAGE_QUALITY", "low"),
            output_format=os.getenv("OPENAI_IMAGE_OUTPUT_FORMAT", "jpeg"),
            output_compression=int(os.getenv("OPENAI_IMAGE_OUTPUT_COMPRESSION", "85")),
            spend_limit_usd=Decimal(os.getenv("OPENAI_SPEND_LIMIT_USD", "5.00")),
            reserve_usd_per_call=Decimal(
                os.getenv("OPENAI_IMAGE_RESERVE_USD_PER_CALL", "0.50")
            ),
            ledger_path=Path(
                os.getenv(
                    "OPENAI_IMAGE_USAGE_LEDGER_PATH",
                    "reports/openai-image-usage.jsonl",
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ImageUsage:
    text_input_tokens: int = 0
    image_input_tokens: int = 0
    image_output_tokens: int = 0

    def estimate_usd(self) -> Decimal:
        return (
            Decimal(self.text_input_tokens) * Decimal("5")
            + Decimal(self.image_input_tokens) * Decimal("8")
            + Decimal(self.image_output_tokens) * Decimal("30")
        ) / MILLION


@dataclass(frozen=True, slots=True)
class ImageResult:
    section_id: str
    image_bytes: bytes
    revised_prompt: str | None
    duration_ms: int
    usage: ImageUsage
    estimated_cost_usd: Decimal


class ImageUsageLedger:
    def __init__(self, path: Path, spend_limit_usd: Decimal) -> None:
        self.path = path
        self.spend_limit_usd = spend_limit_usd

    def total_estimated_usd(self) -> Decimal:
        if not self.path.exists():
            return Decimal("0")
        total = Decimal("0")
        with self.path.open(encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    total += Decimal(json.loads(line)["estimated_cost_usd"])
        return total

    def assert_can_call(self, reserve_usd: Decimal) -> None:
        spent = self.total_estimated_usd()
        if spent + reserve_usd >= self.spend_limit_usd:
            raise OpenAIImageBudgetExceeded(
                "Projected image call would reach or exceed the OpenAI spend limit: "
                f"spent={spent}, reserve={reserve_usd}, limit={self.spend_limit_usd} USD"
            )

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as target:
            target.write(json.dumps(record, ensure_ascii=False) + "\n")


class OpenAIImageAdapter:
    def __init__(
        self,
        settings: ImageSettings,
        ledger: ImageUsageLedger,
        *,
        client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.ledger = ledger
        self.client = client or OpenAI()

    def edit_reference(
        self, *, section_id: str, reference_path: Path, prompt: str
    ) -> ImageResult:
        self.ledger.assert_can_call(self.settings.reserve_usd_per_call)
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        started = time.perf_counter()
        try:
            with reference_path.open("rb") as image_file:
                response = self.client.images.edit(
                    image=image_file,
                    model=self.settings.model,
                    prompt=prompt,
                    n=1,
                    size=self.settings.size,
                    quality=self.settings.quality,
                    output_format=self.settings.output_format,
                    output_compression=self.settings.output_compression,
                    background="opaque",
                )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000)
            self.ledger.append(
                {
                    "section_id": section_id,
                    "model": self.settings.model,
                    "status": "error",
                    "prompt_sha256": prompt_sha256,
                    "duration_ms": duration_ms,
                    "estimated_cost_usd": "0",
                    "error_type": type(exc).__name__,
                }
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000)
        if not response.data or not response.data[0].b64_json:
            raise ValueError("OpenAI image response did not contain base64 image data")
        image_bytes = base64.b64decode(response.data[0].b64_json)
        response_usage = getattr(response, "usage", None)
        details = getattr(response_usage, "input_tokens_details", None)
        usage = ImageUsage(
            text_input_tokens=int(getattr(details, "text_tokens", 0) or 0),
            image_input_tokens=int(getattr(details, "image_tokens", 0) or 0),
            image_output_tokens=int(getattr(response_usage, "output_tokens", 0) or 0),
        )
        cost = usage.estimate_usd()
        self.ledger.append(
            {
                "section_id": section_id,
                "model": self.settings.model,
                "status": "success",
                "prompt_sha256": prompt_sha256,
                "duration_ms": duration_ms,
                "usage": asdict(usage),
                "estimated_cost_usd": str(cost),
                "pricing_source": "openai-gpt-image-2-standard-2026-08-15",
                "error_type": None,
            }
        )
        return ImageResult(
            section_id=section_id,
            image_bytes=image_bytes,
            revised_prompt=response.data[0].revised_prompt,
            duration_ms=duration_ms,
            usage=usage,
            estimated_cost_usd=cost,
        )

    def generate_text(self, *, section_id: str, prompt: str) -> ImageResult:
        """Generate a seed image when the product has no reference image."""

        self.ledger.assert_can_call(self.settings.reserve_usd_per_call)
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        started = time.perf_counter()
        try:
            response = self.client.images.generate(
                model=self.settings.model,
                prompt=prompt,
                n=1,
                size=self.settings.size,
                quality=self.settings.quality,
                output_format=self.settings.output_format,
                output_compression=self.settings.output_compression,
                background="opaque",
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000)
            self.ledger.append(
                {
                    "section_id": section_id,
                    "model": self.settings.model,
                    "status": "error",
                    "input_mode": "text-generate",
                    "prompt_sha256": prompt_sha256,
                    "duration_ms": duration_ms,
                    "estimated_cost_usd": "0",
                    "error_type": type(exc).__name__,
                }
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000)
        if not response.data or not response.data[0].b64_json:
            raise ValueError("OpenAI image response did not contain base64 image data")
        image_bytes = base64.b64decode(response.data[0].b64_json)
        response_usage = getattr(response, "usage", None)
        details = getattr(response_usage, "input_tokens_details", None)
        usage = ImageUsage(
            text_input_tokens=int(getattr(details, "text_tokens", 0) or 0),
            image_input_tokens=int(getattr(details, "image_tokens", 0) or 0),
            image_output_tokens=int(getattr(response_usage, "output_tokens", 0) or 0),
        )
        cost = usage.estimate_usd()
        self.ledger.append(
            {
                "section_id": section_id,
                "model": self.settings.model,
                "status": "success",
                "input_mode": "text-generate",
                "prompt_sha256": prompt_sha256,
                "duration_ms": duration_ms,
                "usage": asdict(usage),
                "estimated_cost_usd": str(cost),
                "pricing_source": "openai-gpt-image-2-standard-2026-08-15",
                "error_type": None,
            }
        )
        return ImageResult(
            section_id=section_id,
            image_bytes=image_bytes,
            revised_prompt=response.data[0].revised_prompt,
            duration_ms=duration_ms,
            usage=usage,
            estimated_cost_usd=cost,
        )
