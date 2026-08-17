from copy import deepcopy

from funding_story_ai.data_repository import DataRepository
from funding_story_ai.validation import StoryValidator


def _valid_content(repository: DataRepository, template_id: str) -> dict:
    template = repository.get_template(template_id)
    return {
        "title_candidates": ["클린포지 R1, 청소 이후의 관리까지 한 흐름으로"],
        "sections": [
            {
                "template_section_id": section["id"],
                "type": section["type"],
                "heading": section["label"],
                "body": "클린포지 R1에 입력된 제품 정보와 미확인 항목을 구분합니다.",
                "source_fields": ["product.name"],
                "image_intent": {
                    "required": section["image_required"],
                    "purpose": "제품 외형과 사용 맥락 제시" if section["image_required"] else "",
                    "visual_hint": section["visual_hint"] if section["image_required"] else "",
                    "source_fields": ["asset_product_hero"]
                    if section["image_required"]
                    else [],
                },
            }
            for section in template["layout"]
        ],
    }


def test_valid_content_matches_t02_contract() -> None:
    repository = DataRepository()
    brief = repository.load_brief("robot-vacuum/brief.json")
    template = repository.get_template("t02_problem_solution_automation")
    content = _valid_content(repository, template["id"])

    repository.validate_story_generation_content(content)
    assert StoryValidator().validate(
        content=content, brief=brief, template=template
    ) == []


def test_validator_flags_unlisted_number_and_template_drift() -> None:
    repository = DataRepository()
    brief = repository.load_brief("robot-vacuum/brief.json")
    template = repository.get_template("t02_problem_solution_automation")
    content = deepcopy(_valid_content(repository, template["id"]))
    content["sections"][0]["body"] = "입력에 없는 99% 만족도를 주장합니다."
    content["sections"][0]["type"] = "offer"
    content["sections"][0]["image_intent"]["required"] = False

    codes = {
        warning.code
        for warning in StoryValidator().validate(
            content=content, brief=brief, template=template
        )
    }
    assert {"unlisted-number", "section-type-mismatch", "image-contract-mismatch"} <= codes


def test_validator_ignores_ordered_list_labels_but_keeps_claim_numbers() -> None:
    repository = DataRepository()
    brief = repository.load_brief("robot-vacuum/brief.json")
    template = repository.get_template("t02_problem_solution_automation")
    content = _valid_content(repository, template["id"])
    content["sections"][0]["body"] = (
        "1. 입력된 제품 정보\n"
        "2) 확인된 기능\n"
        "3. 근거 없이 99% 만족도를 주장"
    )

    warnings = StoryValidator().validate(
        content=content,
        brief=brief,
        template=template,
    )
    number_warnings = [warning for warning in warnings if warning.code == "unlisted-number"]

    assert len(number_warnings) == 1
    assert "99" in number_warnings[0].message
    assert all(label not in number_warnings[0].message for label in ("1", "2", "3"))


def test_validator_flags_promises_created_from_unknown_input() -> None:
    repository = DataRepository()
    brief = repository.load_brief("robot-vacuum/brief.json")
    template = repository.get_template("t02_problem_solution_automation")
    content = _valid_content(repository, template["id"])
    service = next(
        section for section in content["sections"] if section["template_section_id"] == "service"
    )
    service["body"] = "AS 정책은 현재 확인 중이며 추후 공지될 예정입니다."
    service["source_fields"] = ["unknown.as_and_refund_policy"]

    codes = {
        warning.code
        for warning in StoryValidator().validate(
            content=content, brief=brief, template=template
        )
    }
    assert "unsupported-future-commitment" in codes


def test_validator_flags_product_common_sense_and_concept_expansion() -> None:
    repository = DataRepository()
    brief = repository.load_brief("robot-vacuum/brief.json")
    template = repository.get_template("t02_problem_solution_automation")
    content = _valid_content(repository, template["id"])
    content["sections"][3]["body"] = (
        "전면 센서로 경로를 감지하고 도크로 자동 복귀합니다. "
        "정수통 채움과 오수통 비움, 먼지봉투 교체는 수동 관리가 필요합니다."
    )
    content["sections"][4]["body"] = "전용 모바일 앱을 지원합니다."
    content["sections"][7]["body"] = "개발팀은 앱 연동 경험을 갖췄습니다."

    warnings = StoryValidator().validate(
        content=content,
        brief=brief,
        template=template,
    )

    codes = [warning.code for warning in warnings]
    messages = [warning.message for warning in warnings]
    assert codes.count("unsupported-generated-text") >= 6
    assert "source-role-imprecision" in codes
    assert any("도크 자동 복귀" in message for message in messages)
    assert any("정수통 관리 방식" in message for message in messages)
    assert any("오수통 관리 방식" in message for message in messages)
    assert any("먼지봉투 관리 방식" in message for message in messages)
    assert any("앱 연동 경험" in message for message in messages)


def test_validator_requires_explicit_support_for_automatic_dust_emptying() -> None:
    repository = DataRepository()
    brief = repository.load_brief("robot-vacuum/brief.json")
    for feature in brief["features"]:
        if feature["id"] == "feature_all_in_one_dock":
            feature["description"] = feature["description"].replace("자동 먼지 비움", "먼지 비움")
    template = repository.get_template("t02_problem_solution_automation")
    content = _valid_content(repository, template["id"])
    content["sections"][0]["body"] = "도킹 스테이션에서 자동 먼지 비움을 지원합니다."

    warnings = StoryValidator().validate(
        content=content,
        brief=brief,
        template=template,
    )

    assert any("먼지 비움의 자동 동작" in warning.message for warning in warnings)


def test_validator_flags_internal_unknown_identifier_in_prose() -> None:
    repository = DataRepository()
    brief = repository.load_brief("robot-vacuum/brief.json")
    template = repository.get_template("t02_problem_solution_automation")
    content = _valid_content(repository, template["id"])
    content["sections"][6]["body"] = (
        "AS 정책은 입력되지 않았습니다(unknown.as_and_refund_policy)."
    )
    content["sections"][6]["source_fields"] = ["unknown.as_and_refund_policy"]

    codes = {
        warning.code
        for warning in StoryValidator().validate(
            content=content,
            brief=brief,
            template=template,
        )
    }
    assert "internal-identifier-leak" in codes
