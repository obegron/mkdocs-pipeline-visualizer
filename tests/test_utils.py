from mkdocs_pipeline_visualizer.navigation_utils import (
    get_group,
    get_relative_path,
    semantic_version_key,
)
from mkdocs_pipeline_visualizer.rendering_utils import (
    get_script_type,
    render_args,
    render_command,
    render_script,
)


def test_semantic_version_key_handles_invalid_values():
    assert semantic_version_key("not-a-version") == semantic_version_key("0.0.0")


def test_get_group_with_offset():
    path = "catalog/team-a/pipelines/build/my-pipeline.yaml"
    assert get_group(path, (1, -1)) == "team-a/pipelines"


def test_get_relative_path_cross_directory():
    from_path = "catalog/team-a/pipelines/build.md"
    to_path = "catalog/shared/tasks/lint.md"
    assert get_relative_path(from_path, to_path) == "../../shared/tasks/lint.md"


def test_script_type_and_blocks():
    script = "#!/usr/bin/env python\nprint('ok')"
    assert get_script_type(script) == "python"
    assert "```python" in render_script(script)
    assert "```console" in render_command(["echo", "hello"])
    assert "```shell" in render_args(["-x", "foo"])
