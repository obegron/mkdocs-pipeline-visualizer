import json
import re
from collections.abc import Callable, Mapping, Sequence
from html import escape
from typing import Any

ResourcePathMap = dict[str, dict[str, str]]


def format_value(value: Any) -> str:
    """Keep YAML values readable without allowing them to break a table cell."""
    if isinstance(value, (dict, list, bool)) or value is None:
        value = json.dumps(value, ensure_ascii=False)
    return escape(str(value)).replace("|", "&#124;").replace("\n", "<br>")


def code_value(value: Any) -> str:
    return "<code>" + format_value('""' if value == "" else value) + "</code>"


def task_dependencies(task: Mapping[str, Any]) -> list[str]:
    """Explicit ordering plus implicit ordering from task result substitutions."""
    dependencies = list(task.get("runAfter", []))

    def visit(value: Any) -> None:
        if isinstance(value, str):
            dependencies.extend(
                re.findall(r"\$\(tasks\.([a-zA-Z0-9_-]+)\.results\.", value)
            )
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(task)
    return list(dict.fromkeys(dependencies))


def table_with_header(header: str, table_headers: Sequence[str]) -> str:
    col_headers = "|"
    under_line = "|"
    for col in table_headers:
        col_headers += f" {col} |"
        under_line += f" {'-' * len(col)} |"
    return f"{header}\n\n{col_headers}\n{under_line}\n"


def get_script_type(script: str) -> str:
    shebang_dict = {
        "python": "python",
        "ruby": "ruby",
        "perl": "perl",
        "node": "javascript",
        "php": "php",
        "bash": "bash",
        "pwsh": "powershell",
        "lua": "lua",
    }
    lines = script.splitlines()
    if lines and lines[0].startswith("#!"):
        first_line = lines[0]
        for key, language in shebang_dict.items():
            if key in first_line:
                return language

    return "shell"


def render_script(script: str) -> str:
    if not script:
        return ""
    fence = "`" * max(
        3, max((len(run) + 1 for run in re.findall(r"`+", script)), default=3)
    )
    return f"**Script:**\n\n{fence}{get_script_type(script)}\n{script}\n{fence}\n\n"


def render_command(command: Sequence[str]) -> str:
    if not command:
        return ""
    rendered = " ".join(command)
    return f"**Command:**\n\n```console\n{rendered}\n```\n\n"


def render_args(args: Sequence[str]) -> str:
    if not args:
        return ""
    rendered = " ".join(args)
    return f"**Arguments:**\n\n```shell\n{rendered}\n```\n\n"


def render_resource_reference(
    label: str,
    ref_name: str,
    resource_paths: ResourcePathMap,
    from_path: str,
    relative_path_fn: Callable[[str, str], str],
) -> str:
    if ref_name in resource_paths:
        target_path = resource_paths[ref_name]["path"]
        relative_path = relative_path_fn(from_path, target_path)
        return f"**{label}:** [`{ref_name}`]({relative_path})\n\n"
    return f"**{label}:** `{ref_name}`\n\n"


def resource_anchor(resource: Mapping[str, Any]) -> str:
    from hashlib import sha256

    metadata = resource.get("metadata", {})
    key = f"{resource.get('kind', '').lower()}:{metadata.get('name', '')}:{metadata.get('labels', {}).get('app.kubernetes.io/version', '')}"
    return "resource-" + sha256(key.encode()).hexdigest()[:12]
