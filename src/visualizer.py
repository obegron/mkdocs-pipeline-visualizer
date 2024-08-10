import os
import yaml
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files
from mkdocs.config import config_options


class PipelineVisualizer(BasePlugin):

    config_scheme = (
        ("plantuml_graph_direction", config_options.Choice(["TB", "LR"], default="TB")),
        ("plantuml_theme", config_options.Type(str, default="_none_")),
        ("plantuml_graphs", config_options.Type(bool, default=True)),
        ("auto_nav", config_options.Type(bool, default=False))
    )

    def on_config(self, config):
        self.plantuml_graph_direction = (
            "left to right direction"
            if self.config["plantuml_graph_direction"] == "LR"
            else "top to bottom direction"
        )
        self.plantuml_theme = self.config["plantuml_theme"]
        self.plantum_graphs = self.config["plantuml_graphs"]
        self.auto_nav = self.config["auto_nav"]

    def make_graph_from_tasks(self, tasks, final):
        markdown_content = f"```plantuml\n@startuml\n{self.plantuml_graph_direction}\n!theme {self.plantuml_theme}\n"

        task_dependencies = {}
        all_tasks = set()
        tasks_with_dependencies = set()

        # Collect all task dependencies
        for task in tasks:
            task_name = task.get("name", "Unnamed Task")
            run_after = task.get("runAfter", [])
            all_tasks.add(task_name)

            if not run_after:
                markdown_content += f'"Start" --> {task_name}\n'
            else:
                tasks_with_dependencies.add(task_name)
                for dependency in run_after:
                    task_dependencies.setdefault(dependency, []).append(task_name)

        # Generate the task dependency diagram
        for task, dependencies in task_dependencies.items():
            for dependency in dependencies:
                markdown_content += f'"{task}" --> {dependency}\n'

        # Determine the end tasks (tasks with no dependencies after them)
        end_tasks = all_tasks - set(task_dependencies.keys())

        # Connect end tasks to the first "finally" task
        if final:
            finally_task = final[0].get("name", "Finally Task")
            for end_task in end_tasks:
                markdown_content += f'"{end_task}" --> {finally_task}\n'
            for i in range(len(final) - 1):
                current_task = final[i].get("name", "Finally Task")
                next_task = final[i + 1].get("name", "Finally Task")
                markdown_content += f'"{current_task}" --> "{next_task}"\n'

        markdown_content += "@enduml\n```\n"
        return markdown_content

    def format_value(self, value):
        if isinstance(value, list):
            value = "<ul>" + "".join(f"<li>{v}</li>" for v in value) + "</ul>"
        elif isinstance(value, str) and "\n" in value:
            value = value.replace("\n", "<br>")
        return value

    def table_with_header(self, header, table_headers):
        col_headers = "|"
        under_line = "|"
        for col in table_headers:
            col_headers += f" {col} |"
            under_line += f" { '-' * len(col) } |"
        return f"{header}\n\n{col_headers}\n{under_line}\n"

    def visualize_parameters(self, params):
        if not params:
            return "## Parameters\n\nNo parameters\n"
        markdown_content = self.table_with_header(
            "## Parameters", ["Name", "Type", "Description", "Default"]
        )
        for param in params:
            name = param.get("name", "Unnamed Parameter")
            param_type = param.get("type", "String")
            description = self.format_value(
                param.get("description", "No description provided.")
            )
            default = param.get("default", "")
            markdown_content += f"| `{name}` | `{param_type}` | {description} | {f'`{default}`' if default else ''} |\n"
        return markdown_content + "\n"

    def visualize_workspaces(self, workspaces):
        if not workspaces:
            return ""
        markdown_content = self.table_with_header(
            "## Workspaces", ["Name", "Description", "Optional"]
        )
        for workspace in workspaces:
            name = workspace.get("name", "Unnamed Workspace")
            description = self.format_value(workspace.get("description", ""))
            optional = workspace.get("optional", False)
            markdown_content += f"| `{name}` | {description} | { optional } |\n"
        return markdown_content + "\n"

    def visualize_tasks(self, tasks):
        markdown_content = "## Tasks\n\n"
        for task in tasks:
            task_name = task.get("name", "Unnamed Task")
            markdown_content += f"### {task_name}\n\n"

            # Task Reference
            task_ref = task.get("taskRef", {})
            markdown_content += (
                f"**Task Reference:** `{task_ref.get('name', 'Not specified')}`\n\n"
            )

            # Run After
            run_after = task.get("runAfter", [])
            if run_after:
                markdown_content += "**Runs After:**\n\n"
                for dep in run_after:
                    markdown_content += f"- `{dep}`\n"
                markdown_content += "\n"

            # Parameters
            params = task.get("params", [])
            if params:
                markdown_content += self.table_with_header(
                    "**Parameters**", ["Name", "Value"]
                )
                for param in params:
                    name = param.get("name", "Unnamed Parameter")
                    value = self.format_value(param.get("value", ""))
                    if "<br>" in str(value) or "<ul>" in str(value) or value == "":
                        markdown_content += f"| `{name}` | {value} |\n"
                    else:
                        markdown_content += f"| `{name}` | `{value}` |\n"
                markdown_content += "\n"

            # Workspaces
            workspaces = task.get("workspaces", [])
            if workspaces:
                markdown_content += self.table_with_header(
                    "**Workspaces**", ["Name", "Workspace"]
                )
                for workspace in workspaces:
                    name = workspace.get("name", "Unnamed Workspace")
                    workspace_name = workspace.get("workspace", "Not specified")
                    markdown_content += f"| `{name}` | `{workspace_name}` |\n"
                markdown_content += "\n"

            # Environment Variables
            markdown_content += self.visualize_environment(task.get("env", []))
            markdown_content += "---\n\n"

        return markdown_content

    def visualize_environment(self, env):
        if not env:
            return ""
        markdown_content = self.table_with_header(
            "**Environment Variables:**", ["Name", "Value", "Source", "Optional"]
        )
        for var in env:
            name = var.get("name", "Unnamed Variable")
            value = var.get("value", "")
            value_from = var.get("valueFrom", {})

            if value:
                markdown_content += f"| `{name}` | `{value}` |  |  |\n"
            elif "configMapKeyRef" in value_from:
                cm_name = value_from["configMapKeyRef"].get("name", "Not specified")
                cm_key = value_from["configMapKeyRef"].get("key", "Not specified")
                optional = value_from["configMapKeyRef"].get("optional", False)
                markdown_content += f"| `{name}` | `{cm_name}:{cm_key}` | ConfigMap Reference | {optional} |\n"
            elif "fieldRef" in value_from:
                field_path = value_from["fieldRef"].get("fieldPath", "Not specified")
                markdown_content += (
                    f"| `{name}` | `{field_path}` | Field Reference | |\n"
                )
            elif "secretKeyRef" in value_from:
                secret_name = value_from["secretKeyRef"].get("name", "Not specified")
                secret_key = value_from["secretKeyRef"].get("key", "Not specified")
                optional = value_from["secretKeyRef"].get("optional", False)
                markdown_content += f"| `{name}` | `{secret_name}:{secret_key}` | Secret Reference | {optional} |\n"
            else:
                markdown_content += f"| `{name}` | Not specified | Unknown |\n"
        markdown_content += "\n"
        return markdown_content

    def visualize_steps(self, steps):
        markdown_content = "## Steps\n\n"
        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"Step {i}")
            markdown_content += f"### {step_name}\n\n"

            # Image
            image = step.get("image", "Not specified")
            markdown_content += f"**Image:** `{image}`\n\n"

            # Command
            command = step.get("command", [])
            if command:
                markdown_content += "**Command:**\n\n```\n"
                markdown_content += " ".join(command)
                markdown_content += "\n```\n\n"

            # Args
            args = step.get("args", [])
            if args:
                markdown_content += "**Arguments:**\n\n```\n"
                markdown_content += " ".join(args)
                markdown_content += "\n```\n\n"

            # Environment Variables
            markdown_content += self.visualize_environment(step.get("env", []))
        return markdown_content

    def visualize_results(self, results):
        if not results:
            return "\n"
        markdown_content = self.table_with_header("## Results", ["Name", "Description"])
        for result in results:
            name = result.get("name", "Unnamed Result")
            description = result.get("description", "No description provided.")
            markdown_content += f"| `{name}` | {description} |\n"
        return markdown_content + "\n"

    def visualize_usage(self, metadata, spec):
        task_name = metadata.get("name", "Unnamed Task")
        task_display_name = metadata.get("annotations", {}).get(
            "tekton.dev/displayName", task_name
        )

        usage_yaml = {
            "name": task_display_name,
            "taskRef": {"name": task_name},
            "runAfter": ["<TASK_NAME>"],
            "params": [
                {"name": param["name"], "value": "<VALUE>"}
                for param in spec.get("params", [])
                if "default" not in param
            ],
            "workspaces": [
                {"name": ws["name"], "workspace": "<WORKSPACE_NAME>"}
                for ws in spec.get("workspaces", [])
                if not ws.get("optional", False)
            ],
        }

        if not spec.get("workspaces", []):
            usage_yaml.pop("workspaces")

        yaml_str = yaml.dump([usage_yaml], default_flow_style=False)
        usage = "\n".join("    " + line for line in yaml_str.splitlines())
        return f"""
## Usage

This is the minimum configuration required to use the `{task_name}` task in your pipeline.

```yaml
{usage}
```

Placeholders should be replaced with the appropriate values for your specific use case. Refer to the task's documentation for more details on the available parameters and workspaces.
The `runAfter` parameter is optional and only needed if you want to specify task dependencies for flow control.

"""

    def on_files(self, files, config):
        new_files = []
        nav = config['nav']
        nav.append({'pipeline': []})
        nav.append({'task': []})
        for file in files:
            if file.src_path.endswith(".yaml"):
                # Generate the Markdown content from the YAML file
                with open(file.abs_src_path, "r") as f:
                    try:
                        # Load all documents in the YAML file
                        resources = list(yaml.safe_load_all(f))
                    except yaml.YAMLError as e:
                        print(f"Error parsing YAML file {file.src_path}: {e}")
                        continue
                kind = resources[0].get("kind", "").lower()
                if not kind in ["pipeline", "task"]:
                    continue

                markdown_content = self.generate_markdown_content(resources)

                # Ensure the directory structure exists
                os.makedirs(
                    os.path.dirname(file.abs_src_path.replace(".yaml", ".md")),
                    exist_ok=True,
                )

                with open(file.abs_src_path.replace(".yaml", ".md"), "w") as f:
                    f.write(markdown_content)

                # Add entry for the new file
                new_file = File(
                    file.src_path.replace(".yaml", ".md"),
                    file.src_dir,
                    file.dest_dir,
                    config["site_dir"],
                )
                if self.auto_nav:
                    metadata = resources[0].get("metadata", {})
                    task_name = metadata.get("name", "Unnamed Task")
                    task_version = metadata.get("labels", {}).get("app.kubernetes.io/version", "")
                    if task_version:
                        task_version = f" - {task_version}"
                    if kind == "pipeline":
                        nav[1].get("pipeline").append({f"{task_name}{task_version}": file.src_path.replace(".yaml",".md")})
                    if kind == "task":
                        nav[2].get("task").append({f"{task_name}{task_version}": file.src_path.replace(".yaml",".md")})
                new_files.append(new_file)
            else:
                new_files.append(file)

        return Files(new_files)

    def generate_markdown_content(self, resources):
        markdown_content = ""
        for resource in resources:
            kind = resource.get("kind", "")
            metadata = resource.get("metadata", {})
            spec = resource.get("spec", {})
            resource_name = metadata.get("name", "Unnamed Resource")
            markdown_content += f"# {kind}: {resource_name}\n"

            if kind.lower() == "pipeline":
                markdown_content += self.visualize_pipeline(spec)
            elif kind.lower() == "task":
                markdown_content += self.visualize_task(metadata, spec)

            markdown_content += "\n---\n\n"
        return markdown_content

    def visualize_pipeline(self, spec):
        markdown_content = ""
        tasks = spec.get("tasks", [])
        final = spec.get("finally", [])
        if self.plantum_graphs:
            markdown_content += self.make_graph_from_tasks(tasks, final)
        markdown_content += self.visualize_parameters(spec.get("params", []))
        markdown_content += self.visualize_workspaces(spec.get("workspaces", []))
        markdown_content += self.visualize_tasks(tasks)
        if final:
            markdown_content += "## Finally\n\n"
            markdown_content += self.visualize_tasks(final)
        return markdown_content

    def visualize_task(self, metadata, spec):
        markdown_content = (
            f"## Description\n>{spec.get('description','No description')}\n"
        )
        markdown_content += self.visualize_parameters(spec.get("params", []))
        markdown_content += self.visualize_results(spec.get("results", []))
        markdown_content += self.visualize_workspaces(spec.get("workspaces", []))
        markdown_content += self.visualize_steps(spec.get("steps", []))
        markdown_content += self.visualize_usage(metadata, spec)
        return markdown_content
