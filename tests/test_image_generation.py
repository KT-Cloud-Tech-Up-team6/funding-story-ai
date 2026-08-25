import base64
from types import SimpleNamespace

from funding_story_ai.image_generation import ImageSettings, OpenAIImageAdapter


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
        )


def test_image_adapter_edits_reference_and_omits_input_fidelity(tmp_path) -> None:
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"reference")
    settings = ImageSettings()
    images = FakeImages()
    adapter = OpenAIImageAdapter(
        settings,
        client=SimpleNamespace(images=images),
    )

    result = adapter.edit_reference(
        section_id="hero", reference_path=reference, prompt="제품 히어로 이미지"
    )

    assert result.image_bytes == b"fake-image"
    assert "input_fidelity" not in images.kwargs


def test_image_adapter_generates_without_reference_image() -> None:
    settings = ImageSettings()
    images = FakeImages()
    adapter = OpenAIImageAdapter(
        settings,
        client=SimpleNamespace(images=images),
    )

    result = adapter.generate_text(section_id="hero", prompt="가상 제품 이미지")

    assert result.image_bytes == b"generated-image"
    assert "image" not in images.kwargs
