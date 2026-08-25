from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI


@dataclass(frozen=True, slots=True)
class ImageSettings:
    model: str = "gpt-image-2"
    size: str = "1536x1024"
    quality: str = "low"
    output_format: str = "jpeg"
    output_compression: int = 85

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
        )


@dataclass(frozen=True, slots=True)
class ImageResult:
    section_id: str
    image_bytes: bytes
    revised_prompt: str | None


class OpenAIImageAdapter:
    def __init__(
        self,
        settings: ImageSettings,
        *,
        client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or OpenAI()

    def edit_reference(
        self, *, section_id: str, reference_path: Path, prompt: str
    ) -> ImageResult:
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

        if not response.data or not response.data[0].b64_json:
            raise ValueError("OpenAI image response did not contain base64 image data")
        return ImageResult(
            section_id=section_id,
            image_bytes=base64.b64decode(response.data[0].b64_json),
            revised_prompt=response.data[0].revised_prompt,
        )

    def generate_text(self, *, section_id: str, prompt: str) -> ImageResult:
        """Generate a seed image when the product has no reference image."""

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

        if not response.data or not response.data[0].b64_json:
            raise ValueError("OpenAI image response did not contain base64 image data")
        return ImageResult(
            section_id=section_id,
            image_bytes=base64.b64decode(response.data[0].b64_json),
            revised_prompt=response.data[0].revised_prompt,
        )
