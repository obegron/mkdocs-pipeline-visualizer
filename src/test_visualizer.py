import pytest
from mkdocs.structure.files import File, Files
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
    assert plugin.nav_group_tasks_by_category == False
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

    yaml_content = """kind: Pipeline
metadata:
  name: test-pipeline
  labels:
    app.kubernetes.io/version: "0.1"
spec:
  tasks:
    - name: task1
      taskRef:
        name: task-reference"""
    yaml_file = tmp_path / "test_pipeline.yaml"
    yaml_file.write_text(yaml_content)

    mock_file = File(
        path="test_pipeline.yaml",
        src_dir=str(tmp_path),
        dest_dir=str(tmp_path),
        use_directory_urls=False,
    )

    new_file = plugin._process_yaml_file(mock_file, mock_config, {}, {}, {})

    assert new_file is not None
    assert new_file.src_path.endswith(".md")

    md_content = (tmp_path / new_file.src_path).read_text()
    assert "# Pipeline: test-pipeline v0.1" in md_content
    assert "## Tasks" in md_content
    assert "### task1" in md_content


def test_multi_document_yaml_processing(plugin, mock_config, tmp_path):
    plugin.load_config({})
    plugin.on_config(mock_config)

    yaml_content = """kind: Pipeline
metadata:
  name: pipeline1
spec:
  tasks:
    - name: task1
---
kind: Pipeline
metadata:
  name: pipeline2
spec:
  tasks:
    - name: task2"""

    yaml_file = tmp_path / "multi_pipeline.yaml"
    yaml_file.write_text(yaml_content)

    mock_file = File(
        path="multi_pipeline.yaml",
        src_dir=str(tmp_path),
        dest_dir=str(tmp_path),
        use_directory_urls=False,
    )
    new_files = plugin.on_files(Files([mock_file]), mock_config)
    md_files = [f for f in new_files if f.src_path.endswith(".md")]
    assert len(md_files) == 1
    md_content = (tmp_path / md_files[0].src_path).read_text()

    assert "# Pipeline: pipeline1" in md_content
    assert "# Pipeline: pipeline2" in md_content
    assert "### task1" in md_content
    assert "### task2" in md_content


def test_invalid_yaml_handling(plugin, mock_config, tmp_path):
    plugin.load_config({})
    plugin.on_config(mock_config)
    yaml_content = "kind: Pipeline: content"
    yaml_file = tmp_path / "invalid.yaml"
    yaml_file.write_text(yaml_content)

    mock_file = File(
        path="invalid.yaml",
        src_dir=str(tmp_path),
        dest_dir=str(tmp_path),
        use_directory_urls=False,
    )

    new_files = plugin.on_files([mock_file], mock_config)
    md_files = [f for f in new_files if f.src_path.endswith(".md")]
    assert len(md_files) == 0, f"Expected 0 markdown file, but found {len(md_files)}"


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
    task_versions = {
        "task1": {
            "categories": ["Category1"],
            "versions": [("1.0", "path/to/task1.md")],
        }
    }

    mock_nav = []
    plugin._update_navigation(mock_nav, pipeline_versions, task_versions, {})

    assert len(mock_nav) == 3
    assert "Pipelines" in mock_nav[0]
    assert "Tasks" in mock_nav[1]
    assert "StepActions" in mock_nav[2]


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
    # Update task structure to match new format
    task_versions = {
        "task1": {"versions": [("1.0", "path/to/task1.md")], "categories": []}
    }

    mock_nav = []
    plugin._update_navigation(mock_nav, pipeline_versions, task_versions, {})

    assert len(mock_nav) == 3
    assert "CustomPipelines" in mock_nav[0]
    assert "CustomTasks" in mock_nav[1]
    assert "StepActions" in mock_nav[2]


def test_add_to_versions_no_version(plugin):
    plugin.load_config({"log_level": "DEBUG"})
    plugin.on_config(mock_config)
    resource = {"metadata": {"name": "no-version-pipeline"}}
    new_file = File("pipelines/no-version-pipeline.md", "", "", "")
    pipeline_versions = {}
    task_versions = {}

    plugin._add_to_versions(
        resource, new_file, "pipeline", pipeline_versions, task_versions, {}
    )

    assert "" in pipeline_versions
    assert "no-version-pipeline" in pipeline_versions[""]
    assert len(pipeline_versions[""]["no-version-pipeline"]) == 1
    assert pipeline_versions[""]["no-version-pipeline"][0][0] == ""


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

    plugin._add_to_versions(
        resource, new_file, "pipeline", pipeline_versions, task_versions, {}
    )

    assert "" in pipeline_versions
    assert "version1-pipeline" in pipeline_versions[""]
    # Use os.path.normpath on both sides
    expected_path = os.path.normpath("pipelines/version1-pipeline.md")
    actual_path = os.path.normpath(pipeline_versions[""]["version1-pipeline"][0][1])
    assert actual_path == expected_path


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

    plugin._add_to_versions(resource, new_file, "pipeline", pipeline_versions, {}, {})

    assert "group1/group2" in pipeline_versions
    assert "grouped-pipeline" in pipeline_versions["group1/group2"]


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

    plugin._add_to_versions(resource1, new_file1, "task", {}, task_versions, {})
    plugin._add_to_versions(resource2, new_file2, "task", {}, task_versions, {})

    assert "multi-version-task" in task_versions
    assert "versions" in task_versions["multi-version-task"]
    assert len(task_versions["multi-version-task"]["versions"]) == 2


def test_add_to_versions_with_invalid_grouping_offset(plugin):
    plugin.nav_pipeline_grouping_offset = (-1, 1)
    resource = {
        "metadata": {
            "name": "grouped-pipeline",
            "labels": {"app.kubernetes.io/version": "1.0.0"},
        }
    }
    new_file = File("group1/group2/pipelines/grouped-pipeline.md", "", "", "")
    pipeline_versions = {}

    plugin._add_to_versions(resource, new_file, "pipeline", pipeline_versions, {}, {})

    assert "" in pipeline_versions
    assert "grouped-pipeline" in pipeline_versions[""]
    # Use os.path.normpath on both sides
    expected_path = os.path.normpath("group1/group2/pipelines/grouped-pipeline.md")
    actual_path = os.path.normpath(pipeline_versions[""]["grouped-pipeline"][0][1])
    assert actual_path == expected_path


def test_task_category_grouping(plugin, mock_config):
    plugin.load_config({"nav_group_tasks_by_category": True})
    plugin.on_config(mock_config)

    task_metadata = {
        "metadata": {
            "name": "test-task",
            "annotations": {"tekton.dev/categories": "Code Quality, Testing"},
        }
    }

    categories = plugin._get_task_categories(task_metadata.get("metadata"))
    assert categories == ["Code Quality", "Testing"]


def test_task_without_category(plugin, mock_config):
    plugin.load_config({"nav_group_tasks_by_category": True})
    plugin.on_config(mock_config)

    task_metadata = {"metadata": {"name": "test-task"}}

    categories = plugin._get_task_categories(task_metadata.get("metadata"))
    assert categories == []


def test_add_to_versions_with_category(plugin, mock_config):
    plugin.load_config({"nav_group_tasks_by_category": True})
    plugin.on_config(mock_config)

    task = {
        "kind": "Task",
        "metadata": {
            "name": "test-task",
            "annotations": {"tekton.dev/categories": "Testing"},
        },
    }

    pipeline_versions = {}
    task_versions = {}
    new_file = File("test-task.md", "", "", "")

    plugin._add_to_versions(task, new_file, "task", pipeline_versions, task_versions, {})

    assert "test-task" in task_versions
    assert task_versions["test-task"]["categories"] == ["Testing"]
    assert len(task_versions["test-task"]["versions"]) == 1
