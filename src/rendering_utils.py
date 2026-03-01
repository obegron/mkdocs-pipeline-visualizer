def format_value(value):
    if isinstance(value, list):
        value = "<ul>" + "".join(f"<li>`{v}`</li>" for v in value) + "</ul>"
    elif isinstance(value, str) and "\n" in value:
        value = value.replace("\n", "<br>")
    return value


def table_with_header(header, table_headers):
    col_headers = "|"
    under_line = "|"
    for col in table_headers:
        col_headers += f" {col} |"
        under_line += f" {'-' * len(col)} |"
    return f"{header}\n\n{col_headers}\n{under_line}\n"


def get_script_type(script):
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
        for key in shebang_dict:
            if key in first_line:
                return shebang_dict[key]

    return "shell"


def render_script(script):
    if not script:
        return ""
    return f"**Script:**\n\n```{get_script_type(script)}\n{script}\n```\n\n"


def render_command(command):
    if not command:
        return ""
    rendered = " ".join(command)
    return f"**Command:**\n\n```console\n{rendered}\n```\n\n"


def render_args(args):
    if not args:
        return ""
    rendered = " ".join(args)
    return f"**Arguments:**\n\n```shell\n{rendered}\n```\n\n"


def render_resource_reference(label, ref_name, resource_paths, from_path, relative_path_fn):
    if ref_name in resource_paths:
        target_path = resource_paths[ref_name]["path"]
        relative_path = relative_path_fn(from_path, target_path)
        return f"**{label}:** [`{ref_name}`]({relative_path})\n\n"
    return f"**{label}:** `{ref_name}`\n\n"
