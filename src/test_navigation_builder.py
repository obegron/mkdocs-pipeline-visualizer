import logging

from .navigation_builder import NavigationBuilder


def _builder(**overrides):
    params = {
        "logger": logging.getLogger("test.navigation_builder"),
        "nav_section_pipelines": "Pipelines",
        "nav_section_tasks": "Tasks",
        "nav_section_stepactions": "StepActions",
        "nav_group_tasks_by_category": False,
        "nav_category_mapping": {},
        "nav_hide_empty_sections": False,
    }
    params.update(overrides)
    return NavigationBuilder(**params)


def test_update_navigation_builds_sections():
    builder = _builder()
    nav = []
    pipeline_versions = {"": {"p1": [("1.0.0", "pipelines/p1.md")]}}
    task_versions = {"t1": {"versions": [("1.0.0", "tasks/t1.md")], "categories": []}}
    stepaction_versions = {"s1": [("1.0.0", "steps/s1.md")]}

    builder.update_navigation(nav, pipeline_versions, task_versions, stepaction_versions)

    assert "Pipelines" in nav[0]
    assert "Tasks" in nav[1]
    assert "StepActions" in nav[2]


def test_update_navigation_groups_tasks_by_category_with_mapping():
    builder = _builder(
        nav_group_tasks_by_category=True,
        nav_category_mapping={"Code Quality": "Quality"},
    )
    nav = []
    pipeline_versions = {}
    task_versions = {
        "lint-task": {
            "versions": [("1.0.0", "tasks/lint.md")],
            "categories": ["Code Quality"],
        }
    }

    builder.update_navigation(nav, pipeline_versions, task_versions, {})

    tasks_section = nav[1]["Tasks"]
    assert tasks_section[0] == {"Quality": [{"lint-task": "tasks/lint.md"}]}


def test_update_navigation_hides_empty_sections():
    builder = _builder(nav_hide_empty_sections=True)
    nav = []

    builder.update_navigation(nav, {}, {}, {})

    assert nav == []
