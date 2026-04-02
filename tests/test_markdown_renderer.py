import logging

from mkdocs_pipeline_visualizer.markdown_renderer import MarkdownRenderer
from mkdocs_pipeline_visualizer.navigation_utils import get_relative_path


def _renderer(source_path="pipelines/example.md", include_cli_usage=True):
    return MarkdownRenderer(
        logger=logging.getLogger("test.markdown_renderer"),
        plantuml_graphs=False,
        plantuml_graph_direction="top to bottom direction",
        plantuml_theme="_none_",
        include_cli_usage=include_cli_usage,
        task_paths={"task-a": {"version": "1.0.0", "path": "tasks/task-a.md"}},
        stepaction_paths={"step-a": {"version": "1.0.0", "path": "steps/step-a.md"}},
        relative_path_fn=get_relative_path,
        source_path=source_path,
    )


def test_generate_markdown_content_links_task_reference():
    renderer = _renderer(source_path="pipelines/demo.md")
    resources = [
        {
            "kind": "Pipeline",
            "metadata": {"name": "demo"},
            "spec": {"tasks": [{"name": "build", "taskRef": {"name": "task-a"}}]},
        }
    ]

    content = renderer.generate_markdown_content(resources)

    assert "# Pipeline: demo" in content
    assert "**Task Reference:** [`task-a`](../tasks/task-a.md)" in content


def test_generate_cli_command_skips_defaults_and_optional_workspaces():
    renderer = _renderer()
    metadata = {"name": "task-demo"}
    spec = {
        "params": [{"name": "required"}, {"name": "with-default", "default": "x"}],
        "workspaces": [{"name": "source"}, {"name": "cache", "optional": True}],
    }

    cmd = renderer.generate_cli_command(metadata, spec, kind="task")

    assert "tkn task start task-demo" in cmd
    assert "-p required=<REQUIRED>" in cmd
    assert "with-default" not in cmd
    assert "-w source=<SOURCE>" in cmd
    assert "-w cache" not in cmd


def test_visualize_stepaction_includes_script_block():
    renderer = _renderer()
    metadata = {"name": "step-a"}
    spec = {"script": "#!/usr/bin/env python\nprint('ok')"}

    content = renderer.visualize_stepaction(metadata, spec)

    assert "```python" in content
    assert "print('ok')" in content
