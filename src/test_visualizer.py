import pytest
from mkdocs.structure.files import File
from .visualizer import PipelineVisualizer
import os
import logging


@pytest.fixture
def plugin():
    return PipelineVisualizer()


@pytest.fixture
def mock_config():
    return {
        "site_dir": "",
        "nav": [],
        "plugins": [{"pipeline-visualizer": {}}],  # Empty config to use defaults
    }


def test_default_config_options(plugin, mock_config):
    plugin.load_config({})
    plugin.on_config(mock_config)

    assert plugin.plantuml_graph_direction == "top to bottom direction"
    assert plugin.plantuml_theme == "_none_"
    assert plugin.plantuml_graphs == True
    assert plugin.nav_generation == True
    assert plugin.nav_section_pipelines == "Pipelines"
    assert plugin.nav_section_tasks == "Tasks"
    assert plugin.nav_pipeline_grouping_offset == None
    assert plugin.nav_task_grouping_offset == None
    assert plugin.logger.level == logging.INFO


def test_custom_config_options(plugin):
    custom_config = {
        "plantuml_graph_direction": "LR",
        "plantuml_theme": "test_theme",
        "plantuml_graphs": False,
        "nav_generation": False,
        "nav_section_pipelines": "CustomPipelines",
        "nav_section_tasks": "CustomTasks",
        "nav_pipeline_grouping_offset": "0:-1",
        "nav_task_grouping_offset": "1:-2",
        "log_level": "DEBUG",
    }

    plugin.load_config(custom_config)
    plugin.on_config({})

    assert plugin.plantuml_graph_direction == "left to right direction"
    assert plugin.plantuml_theme == "test_theme"
    assert plugin.plantuml_graphs == False
    assert plugin.nav_generation == False
    assert plugin.nav_section_pipelines == "CustomPipelines"
    assert plugin.nav_section_tasks == "CustomTasks"
    assert plugin.nav_pipeline_grouping_offset == (0, -1)
    assert plugin.nav_task_grouping_offset == (1, -2)
    assert plugin.logger.level == logging.DEBUG


def test_markdown_file_creation(plugin, mock_config, tmp_path):
    plugin.load_config(mock_config)
    plugin.on_config(mock_config)

    yaml_content = """
    kind: Pipeline
    metadata:
      name: test-pipeline
      labels:
        app.kubernetes.io/version: "0.1"
    spec:
      tasks:
        - name: task1
          taskRef:
            name: task-reference
    """
    yaml_file = tmp_path / "test_pipeline.yaml"
    yaml_file.write_text(yaml_content)

    mock_file = File(
        path="test_pipeline.yaml",
        src_dir=str(tmp_path),
        dest_dir=str(tmp_path),
        use_directory_urls=False,
    )

    new_file = plugin.process_yaml_file(mock_file, mock_config, {}, {})

    assert new_file is not None
    assert new_file.src_path.endswith(".md")

    md_content = (tmp_path / new_file.src_path).read_text()
    assert "# Pipeline: test-pipeline v0.1" in md_content
    assert "## Tasks" in md_content
    assert "### task1" in md_content


def test_nav_default_structure_generation(plugin, mock_config):
    plugin.load_config({})
    plugin.on_config(mock_config)

    pipeline_versions = {
        "group1": {
            "pipeline1": [("1.0", "path/to/pipeline1.md")],
            "pipeline2": [
                ("2.0", "path/to/pipeline2.md"),
                ("1.0", "path/to/pipeline2_old.md"),
            ],
        }
    }
    task_versions = {"group2": {"task1": [("1.0", "path/to/task1.md")]}}

    mock_nav = []

    plugin.update_navigation(mock_nav, pipeline_versions, task_versions)

    assert len(mock_nav) == 2
    assert "Pipelines" in mock_nav[0]
    assert "Tasks" in mock_nav[1]

    pipelines_section = mock_nav[0]["Pipelines"]
    tasks_section = mock_nav[1]["Tasks"]

    assert "group1" in pipelines_section[0]
    assert "pipeline1" in pipelines_section[0]["group1"][0]
    assert "pipeline2" in pipelines_section[0]["group1"][1]
    assert len(pipelines_section[0]["group1"][1]["pipeline2"]) == 2

    assert "group2" in tasks_section[0]
    assert "task1" in tasks_section[0]["group2"][0]


def test_nav_structure_generation(plugin, mock_config):
    custom_config = {
        "nav_section_pipelines": "CustomPipelines",
        "nav_section_tasks": "CustomTasks",
    }
    plugin.load_config(custom_config)
    plugin.on_config(mock_config)

    pipeline_versions = {
        "group1": {
            "pipeline1": [("1.0", "path/to/pipeline1.md")],
            "pipeline2": [
                ("2.0", "path/to/pipeline2.md"),
                ("1.0", "path/to/pipeline2_old.md"),
            ],
        }
    }
    task_versions = {"group2": {"task1": [("1.0", "path/to/task1.md")]}}

    mock_nav = []
    plugin.update_navigation(mock_nav, pipeline_versions, task_versions)

    assert len(mock_nav) == 2
    assert "CustomPipelines" in mock_nav[0]
    assert "CustomTasks" in mock_nav[1]

    pipelines_section = mock_nav[0]["CustomPipelines"]
    tasks_section = mock_nav[1]["CustomTasks"]

    assert "group1" in pipelines_section[0]
    assert "pipeline1" in pipelines_section[0]["group1"][0]
    assert "pipeline2" in pipelines_section[0]["group1"][1]
    assert len(pipelines_section[0]["group1"][1]["pipeline2"]) == 2

    assert "group2" in tasks_section[0]
    assert "task1" in tasks_section[0]["group2"][0]


def test_add_to_versions_no_version(plugin):
    plugin.load_config({"log_level": "DEBUG"})
    plugin.on_config(mock_config)
    resource = {"metadata": {"name": "no-version-pipeline"}}
    new_file = File("pipelines/no-version-pipeline.md", "", "", "")
    pipeline_versions = {}
    task_versions = {}

    plugin.add_to_versions(
        resource, new_file, "pipeline", pipeline_versions, task_versions
    )

    assert "" in pipeline_versions
    assert "no-version-pipeline" in pipeline_versions[""]
    assert pipeline_versions[""]["no-version-pipeline"] == [
        ("", os.path.normpath("pipelines/no-version-pipeline.md"))
    ]


def test_add_to_versions(plugin):
    plugin.load_config({"log_level": "DEBUG"})
    plugin.on_config(mock_config)
    resource = {
        "metadata": {
            "name": "version1-pipeline",
            "labels": {"app.kubernetes.io/version": "1.0.0"},
        }
    }
    new_file = File("pipelines/version1-pipeline.md", "", "", "")
    pipeline_versions = {}
    task_versions = {}

    plugin.add_to_versions(
        resource, new_file, "pipeline", pipeline_versions, task_versions
    )

    assert "" in pipeline_versions
    assert "version1-pipeline" in pipeline_versions[""]
    assert pipeline_versions[""]["version1-pipeline"] == [
        ("1.0.0", os.path.normpath("pipelines/version1-pipeline.md"))
    ]


def test_add_to_versions_with_grouping_offset(plugin):
    plugin.nav_pipeline_grouping_offset = (0, -1)
    resource = {
        "metadata": {
            "name": "grouped-pipeline",
            "labels": {"app.kubernetes.io/version": "1.0.0"},
        }
    }
    new_file = File("group1/group2/pipelines/grouped-pipeline.md", "", "", "")
    pipeline_versions = {}

    plugin.add_to_versions(resource, new_file, "pipeline", pipeline_versions, {})

    assert os.path.normpath("group1/group2") in pipeline_versions
    assert "grouped-pipeline" in pipeline_versions[os.path.normpath("group1/group2")]
    assert pipeline_versions[os.path.normpath("group1/group2")]["grouped-pipeline"] == [
        ("1.0.0", os.path.normpath("group1/group2/pipelines/grouped-pipeline.md"))
    ]


def test_add_to_versions_multiple_versions(plugin):
    plugin.load_config({"log_level": "DEBUG"})
    plugin.on_config(mock_config)
    resource1 = {
        "metadata": {
            "name": "multi-version-task",
            "labels": {"app.kubernetes.io/version": "1.0.0"},
        }
    }
    resource2 = {
        "metadata": {
            "name": "multi-version-task",
            "labels": {"app.kubernetes.io/version": "1.1.0"},
        }
    }
    new_file1 = File("tasks/multi-version-task-1.0.0.md", "", "", "")
    new_file2 = File("tasks/multi-version-task-1.1.0.md", "", "", "")
    task_versions = {}

    plugin.add_to_versions(resource1, new_file1, "task", {}, task_versions)
    plugin.add_to_versions(resource2, new_file2, "task", {}, task_versions)

    assert "" in task_versions
    assert "multi-version-task" in task_versions[""]
    assert task_versions[""]["multi-version-task"] == [
        ("1.0.0", os.path.normpath("tasks/multi-version-task-1.0.0.md")),
        ("1.1.0", os.path.normpath("tasks/multi-version-task-1.1.0.md")),
    ]


def test_add_to_versions_with_invalid_grouping_offset(plugin):
    # invalid settings should place pipeline in /
    plugin.nav_pipeline_grouping_offset = (-1, 1)
    resource = {
        "metadata": {
            "name": "grouped-pipeline",
            "labels": {"app.kubernetes.io/version": "1.0.0"},
        }
    }
    new_file = File("group1/group2/pipelines/grouped-pipeline.md", "", "", "")
    pipeline_versions = {}

    plugin.add_to_versions(resource, new_file, "pipeline", pipeline_versions, {})

    assert "" in pipeline_versions
    assert "grouped-pipeline" in pipeline_versions[""]
    assert pipeline_versions[""]["grouped-pipeline"] == [
        ("1.0.0", os.path.normpath("group1/group2/pipelines/grouped-pipeline.md"))
    ]
