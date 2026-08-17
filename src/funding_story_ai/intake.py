from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

IntakeStage = Literal[
    "initial",
    "primary-details",
    "secondary-details",
    "combined-details",
    "confirmation",
    "ready-to-generate",
]


class StoryIntakeState(TypedDict, total=False):
    """Product-independent state used by the clarification graph."""

    initial_message: str
    product_image_attached: bool
    key_strengths: list[str]
    target_supporters: list[str]
    trust_elements: list[str]
    maker_team_intro: str | None
    primary_semantic_complete: bool
    secondary_semantic_complete: bool
    primary_answered_explicitly: bool
    secondary_answered_explicitly: bool
    combined_answered_explicitly: bool
    prefer_combined_question: bool
    skip_remaining_questions: bool
    confirmed: bool
    generation_start_trigger: Literal["explicit-confirmation", "explicit-skip"]
    stage: IntakeStage
    requested_fields: list[str]


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_items(value: object) -> bool:
    return isinstance(value, list) and any(_has_text(item) for item in value)


def _primary_complete(state: StoryIntakeState) -> bool:
    return bool(state.get("primary_semantic_complete")) or (
        _has_items(state.get("key_strengths"))
        and _has_items(state.get("target_supporters"))
    )


def _secondary_complete(state: StoryIntakeState) -> bool:
    return bool(state.get("secondary_semantic_complete")) or (
        _has_items(state.get("trust_elements"))
        and _has_text(state.get("maker_team_intro"))
    )


def route_intake(
    state: StoryIntakeState,
) -> Command[
    Literal[
        "ask_initial",
        "ask_primary",
        "ask_secondary",
        "ask_combined",
        "confirm",
        "ready",
    ]
]:
    """Route to the smallest safe next step; generation never starts implicitly."""

    if not _has_text(state.get("initial_message")):
        return Command(goto="ask_initial")
    if state.get("skip_remaining_questions", False):
        return Command(goto="ready")

    primary_complete = _primary_complete(state) or bool(
        state.get("primary_answered_explicitly")
    )
    secondary_complete = _secondary_complete(state) or bool(
        state.get("secondary_answered_explicitly")
    )
    if state.get("combined_answered_explicitly"):
        primary_complete = True
        secondary_complete = True

    if (
        state.get("prefer_combined_question")
        and not primary_complete
        and not secondary_complete
    ):
        return Command(goto="ask_combined")
    if not primary_complete:
        return Command(goto="ask_primary")
    if not secondary_complete:
        return Command(goto="ask_secondary")
    if not state.get("confirmed", False):
        return Command(goto="confirm")
    return Command(goto="ready")


def ask_initial(_: StoryIntakeState) -> StoryIntakeState:
    return {
        "stage": "initial",
        "requested_fields": ["initial_message", "product_image"],
    }


def ask_primary(_: StoryIntakeState) -> StoryIntakeState:
    return {
        "stage": "primary-details",
        "requested_fields": ["key_strengths", "target_supporters"],
    }


def ask_secondary(_: StoryIntakeState) -> StoryIntakeState:
    return {
        "stage": "secondary-details",
        "requested_fields": ["trust_elements", "maker_team_intro"],
    }


def ask_combined(_: StoryIntakeState) -> StoryIntakeState:
    return {
        "stage": "combined-details",
        "requested_fields": [
            "key_strengths",
            "target_supporters",
            "trust_elements",
            "maker_team_intro",
        ],
    }


def confirm(_: StoryIntakeState) -> StoryIntakeState:
    return {"stage": "confirmation", "requested_fields": ["confirmed"]}


def ready(state: StoryIntakeState) -> StoryIntakeState:
    trigger: Literal["explicit-confirmation", "explicit-skip"] = (
        "explicit-skip"
        if state.get("skip_remaining_questions", False)
        else "explicit-confirmation"
    )
    return {
        "stage": "ready-to-generate",
        "requested_fields": [],
        "generation_start_trigger": trigger,
    }


def question_prompt(stage: IntakeStage, profile: dict[str, Any]) -> str:
    """Compose a category-aware question without coupling examples to routing."""

    guidance = profile["semantic_slot_guidance"]
    stage_slots = {
        "primary-details": ("key_strengths", "target_supporters"),
        "secondary-details": ("trust_elements", "maker_team_intro"),
        "combined-details": (
            "key_strengths",
            "target_supporters",
            "trust_elements",
            "maker_team_intro",
        ),
    }
    if stage == "initial":
        return "제품과 만들고 싶은 펀딩 스토리를 설명해 주세요."
    if stage == "confirmation":
        return "정리된 제품 정보로 스토리를 생성할까요?"
    if stage == "ready-to-generate":
        return ""
    examples = [
        guidance[slot]["question_examples"][0]
        for slot in stage_slots[stage]
        if guidance[slot]["question_examples"]
    ]
    return " ".join(examples)


def build_intake_graph():
    builder = StateGraph(StoryIntakeState)
    builder.add_node("route", route_intake)
    builder.add_node("ask_initial", ask_initial)
    builder.add_node("ask_primary", ask_primary)
    builder.add_node("ask_secondary", ask_secondary)
    builder.add_node("ask_combined", ask_combined)
    builder.add_node("confirm", confirm)
    builder.add_node("ready", ready)
    builder.add_edge(START, "route")
    for node in (
        "ask_initial",
        "ask_primary",
        "ask_secondary",
        "ask_combined",
        "confirm",
        "ready",
    ):
        builder.add_edge(node, END)
    return builder.compile()
