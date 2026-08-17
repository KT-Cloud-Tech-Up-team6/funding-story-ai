from funding_story_ai.data_repository import DataRepository
from funding_story_ai.intake import build_intake_graph, question_prompt


def test_intake_starts_with_product_request() -> None:
    result = build_intake_graph().invoke({})
    assert result["stage"] == "initial"
    assert result["requested_fields"] == ["initial_message", "product_image"]


def test_missing_primary_information_is_requested_first() -> None:
    result = build_intake_graph().invoke(
        {"initial_message": "로봇청소기 스토리를 만들어 줘"}
    )
    assert result["stage"] == "primary-details"
    assert result["requested_fields"] == ["key_strengths", "target_supporters"]


def test_secondary_information_follows_primary_information() -> None:
    result = build_intake_graph().invoke(
        {
            "initial_message": "로봇청소기 스토리를 만들어 줘",
            "primary_semantic_complete": True,
        }
    )
    assert result["stage"] == "secondary-details"
    assert result["requested_fields"] == ["trust_elements", "maker_team_intro"]


def test_combined_question_is_an_explicit_policy_choice() -> None:
    result = build_intake_graph().invoke(
        {
            "initial_message": "로봇청소기 스토리를 만들어 줘",
            "prefer_combined_question": True,
        }
    )
    assert result["stage"] == "combined-details"
    assert result["requested_fields"] == [
        "key_strengths",
        "target_supporters",
        "trust_elements",
        "maker_team_intro",
    ]


def test_complete_information_requires_confirmation() -> None:
    result = build_intake_graph().invoke(
        {
            "initial_message": "제품·타깃·신뢰·팀 정보가 모두 포함된 설명",
            "primary_semantic_complete": True,
            "secondary_semantic_complete": True,
        }
    )
    assert result["stage"] == "confirmation"


def test_generation_starts_only_after_confirmation_or_explicit_skip() -> None:
    confirmed = build_intake_graph().invoke(
        {
            "initial_message": "제품 설명",
            "primary_semantic_complete": True,
            "secondary_semantic_complete": True,
            "confirmed": True,
        }
    )
    assert confirmed["stage"] == "ready-to-generate"
    assert confirmed["generation_start_trigger"] == "explicit-confirmation"

    skipped = build_intake_graph().invoke(
        {
            "initial_message": "제품 설명",
            "skip_remaining_questions": True,
        }
    )
    assert skipped["stage"] == "ready-to-generate"
    assert skipped["generation_start_trigger"] == "explicit-skip"


def test_profile_examples_are_kept_outside_routing_logic() -> None:
    profile = DataRepository().get_category_profile("robot-vacuum-ko-v1")
    prompt = question_prompt("primary-details", profile)
    assert "흡입" in prompt
    assert "주거 환경" in prompt
