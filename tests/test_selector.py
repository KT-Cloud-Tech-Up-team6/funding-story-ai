from funding_story_ai.data_repository import DataRepository
from funding_story_ai.selector import TemplateSelector


def test_cleanforge_brief_selects_problem_solution_automation_template() -> None:
    repository = DataRepository()
    brief = repository.load_brief("robot-vacuum/brief.json")
    selection = TemplateSelector().select(brief, repository.load_templates())

    assert selection.template_id == "t02_problem_solution_automation"
    assert selection.scores[selection.template_id] == max(selection.scores.values())
    assert "automation/problem signals" in " ".join(selection.reasons)


def test_category_profile_applies_only_declared_soft_boosts() -> None:
    repository = DataRepository()
    brief = repository.load_brief("robot-vacuum/brief.json")
    profile = repository.get_category_profile("robot-vacuum-ko-v1")
    baseline = TemplateSelector().select(brief, repository.load_templates())
    selection = TemplateSelector().select(
        brief,
        repository.load_templates(),
        soft_boosts=profile["template_soft_boosts"],
    )

    assert selection.scores["t04_full_campaign"] == (
        baseline.scores["t04_full_campaign"] + 4
    )
    assert selection.scores["t02_problem_solution_automation"] == (
        baseline.scores["t02_problem_solution_automation"] + 3
    )
    assert "category profile soft boost" in " ".join(selection.reasons)
