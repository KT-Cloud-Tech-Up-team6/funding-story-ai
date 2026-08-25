from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

from .config import RuntimeSettings


@dataclass(frozen=True, slots=True)
class GenerationResult:
    model: str
    data: dict[str, Any]


def _error_code(exc: Exception) -> int | None:
    for attribute in ("code", "status_code"):
        value = getattr(exc, attribute, None)
        if callable(value):
            value = value()
        value = getattr(value, "value", value)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def is_model_access_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return _error_code(exc) in {401, 403, 404, 408, 429, 500, 502, 503, 504}


class GeminiAdapter:
    def __init__(
        self,
        settings: RuntimeSettings,
        *,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.client = client or genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.location,
            http_options=types.HttpOptions(api_version="v1"),
        )
        self.sleep = sleep

    def generate_json(
        self,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> GenerationResult:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        return self._generate_json(
            contents=prompt,
            response_schema=response_schema,
        )

    def generate_multimodal_json(
        self,
        *,
        prompt: str,
        images: list[tuple[bytes, str]],
        response_schema: dict[str, Any],
    ) -> GenerationResult:
        """Generate schema-constrained JSON from text and in-memory images."""
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        if not images:
            return self.generate_json(
                prompt=prompt,
                response_schema=response_schema,
            )
        parts: list[Any] = [types.Part.from_text(text=prompt)]
        for image_bytes, mime_type in images:
            if not image_bytes:
                raise ValueError("image bytes must not be empty")
            if not mime_type.startswith("image/"):
                raise ValueError(f"unsupported image mime type: {mime_type}")
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
        return self._generate_json(
            contents=[types.Content(role="user", parts=parts)],
            response_schema=response_schema,
        )

    def _generate_json(
        self,
        *,
        contents: Any,
        response_schema: dict[str, Any],
    ) -> GenerationResult:
        last_access_error: Exception | None = None

        for primary_attempt in range(1, self.settings.primary_access_attempts + 1):
            try:
                return self._call(
                    model=self.settings.primary_model,
                    contents=contents,
                    response_schema=response_schema,
                )
            except Exception as exc:
                if not is_model_access_error(exc):
                    raise
                last_access_error = exc
                if primary_attempt < self.settings.primary_access_attempts:
                    self.sleep(min(2 ** (primary_attempt - 1), 8))

        try:
            return self._call(
                model=self.settings.fallback_model,
                contents=contents,
                response_schema=response_schema,
            )
        except Exception as fallback_error:
            if last_access_error is not None:
                fallback_error.add_note(
                    "Primary model failed "
                    f"{self.settings.primary_access_attempts} access attempts: "
                    f"{type(last_access_error).__name__}"
                )
            raise

    def _call(
        self,
        *,
        model: str,
        contents: Any,
        response_schema: dict[str, Any],
    ) -> GenerationResult:
        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=response_schema,
                max_output_tokens=self.settings.max_output_tokens,
                thinking_config=types.ThinkingConfig(
                    thinking_level=self.settings.thinking_level
                ),
            ),
        )
        data = self._extract_json(response)
        return GenerationResult(
            model=model,
            data=data,
        )

    @staticmethod
    def _extract_json(response: Any) -> dict[str, Any]:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, dict):
            return parsed
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Gemini response did not contain JSON text")
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("Gemini response JSON must be an object")
        return value
