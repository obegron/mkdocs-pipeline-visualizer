import re

import markdown
import pytest
import yaml
from mkdocs.commands.build import build
from mkdocs.config import load_config
from mkdocs.exceptions import PluginError
from mkdocs.structure.files import File, Files

from mkdocs_pipeline_visualizer.rendering_utils import task_dependencies
from mkdocs_pipeline_visualizer.visualizer import PipelineVisualizer
from tests.test_markdown_renderer import _renderer


def test_overview_and_graph_include_result_dependencies_and_parallel_finally():
    renderer = _renderer()
    renderer.plantuml_graphs = True
    spec = {
        "description": "Build and publish a release.",
        "tasks": [
            {"name": "build", "taskRef": {"name": "task-a"}},
            {
                "name": "publish",
                "params": [{"name": "image", "value": "$(tasks.build.results.image)"}],
            },
        ],
        "finally": [{"name": "cleanup"}, {"name": "notify"}],
        "results": [{"name": "image", "value": "$(tasks.build.results.image)"}],
    }
    content = renderer.visualize_pipeline(spec)
    assert content.startswith(spec["description"])
    assert "task_0 --> task_1" in content
    assert 'rectangle "Start" as pipeline_start' in content
    assert "pipeline_start --> task_0" in content
    assert "task_0 ..> final_phase" not in content
    assert "task_1 ..> final_phase" in content
    assert "final_phase --> final_0" in content
    assert "final_phase --> final_1" in content
    assert "final_0 --> final_1" not in content
    assert "$(tasks.build.results.image)" in content
    assert content.count("## Finally") == 1
    html = markdown.markdown(content, extensions=["tables", "fenced_code"])
    for anchor in re.findall(r'href="#([^"]+)"', html):
        assert f'id="{anchor}"' in html


def test_dependencies_walk_nested_values_without_duplicates():
    assert task_dependencies(
        {
            "runAfter": ["a"],
            "params": [
                {"value": {"x": ["$(tasks.a.results.x)", "$(tasks.b.results.y)"]}}
            ],
        }
    ) == ["a", "b"]


@pytest.mark.parametrize("default", ["", False, 0, [], {}, "a|b\n<script>"])
def test_defaults_remain_optional_and_tables_render_four_cells_plus_name(default):
    content = _renderer().visualize_parameters([{"name": "value", "default": default}])
    html = markdown.markdown(content, extensions=["tables"])
    assert html.count("<td>") == 5
    assert "<td>No</td>" in html
    assert "<script>" not in html
    assert "—" not in content


def test_pipeline_usage_is_a_run_object_with_valid_workspace_binding():
    content = _renderer().visualize_usage(
        {"name": "release"},
        {
            "params": [{"name": "files", "type": "array"}],
            "workspaces": [{"name": "source"}],
        },
        "pipeline",
    )
    run = yaml.safe_load(re.search(r"```yaml\n(.*?)```", content, re.DOTALL)[1])
    assert run["apiVersion"] == "tekton.dev/v1"
    assert run["spec"]["workspaces"] == [
        {"name": "source", "persistentVolumeClaim": {"claimName": "<PVC_NAME>"}}
    ]
    assert run["spec"]["params"][0]["value"] == []


def test_steps_show_order_and_stepaction_arguments():
    content = _renderer().visualize_steps(
        [
            {
                "name": "invoke",
                "ref": {"name": "step-a"},
                "params": [{"name": "message", "value": "hello"}],
            }
        ]
    )
    assert "Steps run in the order shown" in content
    assert "../steps/step-a.md" in content
    assert "<code>hello</code>" in content


def test_mixed_documents_index_before_render_and_do_not_write_sources(tmp_path):
    (tmp_path / "mixed.yml").write_text("""kind: Task
metadata: {name: worker}
spec:
  steps:
    - name: invoke
      ref: {name: action}
---
kind: Pipeline
metadata: {name: release}
spec:
  tasks:
    - name: build
      taskRef: {name: worker}
---
kind: ConfigMap
metadata: {name: ignore-me}
""")
    (tmp_path / "action.yaml").write_text(
        "kind: StepAction\nmetadata: {name: action}\nspec: {}"
    )
    plugin = PipelineVisualizer()
    plugin.load_config({})
    config = {
        "site_dir": str(tmp_path / "site"),
        "nav": None,
        "use_directory_urls": False,
    }
    plugin.on_config(config)
    files = Files(
        [
            File(p, str(tmp_path), config["site_dir"], False)
            for p in ["mixed.yml", "action.yaml"]
        ]
    )
    generated = plugin.on_files(files, config)
    pages = [f for f in generated if f.is_documentation_page()]
    assert len(pages) == 2
    content = pages[0].content_string
    assert "action.md#resource-" in content
    assert "mixed.md#resource-" in content
    assert "ignore-me" not in content
    assert not list(tmp_path.glob("*.md"))
    plugin.on_files(Files([]), {"site_dir": config["site_dir"], "nav": []})
    assert not plugin._task_paths
    assert not plugin._stepaction_paths


def test_existing_markdown_is_never_overwritten(tmp_path):
    (tmp_path / "task.yaml").write_text("kind: Task\nmetadata: {name: task}\nspec: {}")
    (tmp_path / "task.md").write_text("Handwritten documentation")
    plugin = PipelineVisualizer()
    plugin.load_config({})
    config = {"site_dir": str(tmp_path / "site"), "nav": []}
    plugin.on_config(config)
    files = Files(
        [
            File(p, str(tmp_path), config["site_dir"], True)
            for p in ["task.yaml", "task.md"]
        ]
    )
    with pytest.raises(PluginError, match="conflicts"):
        plugin.on_files(files, config)
    assert (tmp_path / "task.md").read_text() == "Handwritten documentation"


@pytest.mark.parametrize("directory_urls", [True, False])
def test_strict_mkdocs_build_with_search_and_cross_links(tmp_path, directory_urls):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("# Tekton catalog")
    (docs / "task.yaml").write_text(
        "kind: Task\nmetadata: {name: worker}\nspec: {steps: [{name: hello, image: busybox}]}"
    )
    (docs / "pipeline.yaml").write_text(
        "kind: Pipeline\nmetadata: {name: release}\nspec: {tasks: [{name: build, taskRef: {name: worker}}]}"
    )
    path = tmp_path / "mkdocs.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "site_name": "Catalog",
                "use_directory_urls": directory_urls,
                "plugins": [
                    "search",
                    {
                        "pipeline-visualizer": {
                            "plantuml_graphs": False,
                            "nav_hide_empty_sections": True,
                        }
                    },
                ],
            }
        )
    )
    config = load_config(str(path), strict=True)
    build(config)
    page = (
        tmp_path
        / "site"
        / ("pipeline/index.html" if directory_urls else "pipeline.html")
    )
    html = page.read_text()
    assert "Execution flow" in html
    assert (tmp_path / "site/search/search_index.json").exists()
    assert not (docs / "pipeline.md").exists()


def test_rebuild_removes_deleted_resources_from_navigation(tmp_path):
    path = tmp_path / "task.yaml"
    path.write_text("kind: Task\nmetadata: {name: worker}\nspec: {}")
    plugin = PipelineVisualizer()
    plugin.load_config({"nav_hide_empty_sections": True})
    config = {"site_dir": str(tmp_path / "site"), "nav": [{"Guide": "guide.md"}]}
    plugin.on_config(config)
    files = Files([File("task.yaml", str(tmp_path), config["site_dir"], True)])
    plugin.on_files(files, config)
    first_nav = repr(config["nav"])
    plugin.on_files(files, config)
    assert repr(config["nav"]) == first_nav
    plugin.on_files(Files([]), config)
    assert config["nav"] == [{"Guide": "guide.md"}]


@pytest.mark.parametrize("kind", ["Pipeline", "Task"])
@pytest.mark.parametrize("usage,cli", [(False, True), (True, False), (True, True)])
def test_usage_configuration_controls_generated_reference_pages(kind, usage, cli):
    plugin = PipelineVisualizer()
    plugin.load_config({"include_usage": usage, "include_cli_usage": cli})
    plugin.on_config({})
    content = plugin._generate_markdown_content(
        [{"kind": kind, "metadata": {"name": "production"}, "spec": {}}],
        "production.yaml",
    )
    assert ("<summary>Example invocation</summary>" in content) is usage
    assert ('class="language-yaml"' in content) is usage
    assert ("tkn " in content) is (usage and cli)
    assert "<summary>Resource definition</summary>" in content
    assert "View source YAML" not in content


def test_default_pages_keep_examples_collapsed():
    plugin = PipelineVisualizer()
    plugin.load_config({})
    plugin.on_config({})
    assert plugin.include_usage is True
    content = plugin._generate_markdown_content(
        [{"kind": "Task", "metadata": {"name": "production"}, "spec": {}}],
        "production.yaml",
    )
    assert "## Usage" not in content
    assert "<details><summary>Example invocation</summary>" in content
    assert "<details open" not in content
    assert content.index("<summary>Example invocation</summary>") < content.index(
        "<summary>Resource definition</summary>"
    )
    html = markdown.markdown(content, extensions=["tables", "fenced_code"])
    assert '<pre><code class="language-yaml">' in html


def test_task_outline_introduces_steps_before_interface_and_links_to_details():
    content = _renderer().visualize_task(
        {"name": "build"},
        {
            "description": "Compile source.",
            "params": [{"name": "revision"}],
            "workspaces": [{"name": "source"}],
            "results": [{"name": "image"}],
            "steps": [
                {"name": "compile", "image": "compiler", "script": "compile source"}
            ],
        },
    )
    headings = re.findall(r"^## (.+)$", content, re.MULTILINE)
    assert headings == [
        "Step overview",
        "Parameters",
        "Workspaces",
        "Results",
        "Step details",
    ]
    assert content.count("compile source") == 1
    assert content.index("compile source") > content.index("## Step details")
    html = markdown.markdown(content, extensions=["tables", "fenced_code"])
    for anchor in re.findall(r'href="#([^"]+)"', html):
        assert html.count(f'id="{anchor}"') == 1


@pytest.mark.parametrize("results", [[], [{"name": "output"}]])
def test_stepaction_implementation_has_its_own_heading(results):
    content = _renderer().visualize_stepaction(
        {"name": "action"},
        {"image": "busybox", "results": results, "script": "echo hello"},
    )
    assert (
        content.index("## Execution overview")
        < content.index("**Image:**")
        < content.index("## Parameters")
    )
    assert content.index("## Implementation") < content.index("**Script:**")
    assert content.rsplit("## ", 1)[1].startswith("Implementation")


def test_bindings_and_result_expressions_are_distinct_from_interfaces():
    content = _renderer().visualize_pipeline(
        {
            "params": [{"name": "revision"}],
            "results": [{"name": "image", "value": "$(tasks.build.results.image)"}],
            "tasks": [
                {
                    "name": "build",
                    "taskRef": {"name": "task-a"},
                    "params": [{"name": "ref", "value": "$(params.revision)"}],
                    "workspaces": [{"name": "src", "workspace": "shared"}],
                }
            ],
        }
    )
    assert "## Parameters" in content
    assert "**Parameter bindings:**" in content
    assert "| Task parameter | Supplied value |" in content
    assert "| Task workspace | Pipeline workspace | Subpath |" in content
    assert "| Value expression |" in content
