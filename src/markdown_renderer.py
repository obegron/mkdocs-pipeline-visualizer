import yaml

from .rendering_utils import (
    format_value,
    get_script_type,
    render_args,
    render_command,
    render_resource_reference,
    render_script,
    table_with_header,
)


class MarkdownRenderer:
    def __init__(
        self,
        logger,
        plantuml_graphs,
        plantuml_graph_direction,
        plantuml_theme,
        include_cli_usage,
        task_paths,
        stepaction_paths,
        relative_path_fn,
        source_path,
    ):
        self.logger = logger
        self.plantuml_graphs = plantuml_graphs
        self.plantuml_graph_direction = plantuml_graph_direction
        self.plantuml_theme = plantuml_theme
        self.include_cli_usage = include_cli_usage
        self.task_paths = task_paths
        self.stepaction_paths = stepaction_paths
        self.relative_path_fn = relative_path_fn
        self.source_path = source_path

    def generate_markdown_content(self, resources):
        self.logger.debug("Generating Markdown content for %d resources", len(resources))
        markdown_content = ""
        for resource in resources:
            kind = resource.get("kind", "")
            metadata = resource.get("metadata", {})
            spec = resource.get("spec", {})
            resource_name = metadata.get("name", "Unnamed Resource")
            resource_version = metadata.get("labels", {}).get(
                "app.kubernetes.io/version", ""
            )
            if resource_version:
                resource_version = f" v{resource_version}"

            markdown_content += f"# {kind}: {resource_name}{resource_version}\n"

            if kind.lower() == "pipeline":
                markdown_content += self.visualize_pipeline(spec)
            elif kind.lower() == "task":
                markdown_content += self.visualize_task(metadata, spec)
            elif kind.lower() == "stepaction":
                markdown_content += self.visualize_stepaction(metadata, spec)

            markdown_content += "\n---\n\n"
        return markdown_content

    def visualize_pipeline(self, spec):
        self.logger.debug("Visualizing pipeline")
        markdown_content = ""
        tasks = spec.get("tasks", [])
        final = spec.get("finally", [])
        if self.plantuml_graphs:
            markdown_content += self.make_graph_from_tasks(tasks, final)
        markdown_content += self.visualize_parameters(spec.get("params", []))
        markdown_content += self.visualize_workspaces(spec.get("workspaces", []))
        markdown_content += self.visualize_tasks(tasks)
        if final:
            markdown_content += "## Finally\n\n"
            markdown_content += self.visualize_tasks(final)
        return markdown_content

    def visualize_task(self, metadata, spec):
        self.logger.debug("Visualizing task: %s", metadata.get("name", "Unnamed Task"))
        markdown_content = f"## Description\n>{spec.get('description','No description')}\n"
        markdown_content += self.visualize_parameters(spec.get("params", []))
        markdown_content += self.visualize_results(spec.get("results", []))
        markdown_content += self.visualize_workspaces(spec.get("workspaces", []))
        markdown_content += self.visualize_step_template(spec.get("stepTemplate", []))
        markdown_content += self.visualize_steps(spec.get("steps", []))
        markdown_content += self.visualize_usage(metadata, spec)
        return markdown_content

    def visualize_stepaction(self, metadata, spec):
        self.logger.debug(
            "Visualizing stepaction: %s", metadata.get("name", "Unnamed StepAction")
        )
        markdown_content = f"## Description\n>{spec.get('description','No description')}\n"
        markdown_content += self.visualize_parameters(spec.get("params", []))
        markdown_content += self.visualize_results(spec.get("results", []))

        image = spec.get("image", "Not specified")
        markdown_content += f"\n**Image:** `{image}`\n\n"

        markdown_content += self.render_script(spec.get("script", ""))
        markdown_content += self.render_command(spec.get("command", []))
        markdown_content += self.render_args(spec.get("args", []))
        markdown_content += self.visualize_environment(spec.get("env", []))
        return markdown_content

    def make_graph_from_tasks(self, tasks, final):
        self.logger.debug(
            "Generating graph from %d tasks and %d final tasks", len(tasks), len(final)
        )
        markdown_content = (
            f"```plantuml\n@startuml\n{self.plantuml_graph_direction}\n"
            f"!theme {self.plantuml_theme}\n"
        )

        task_dependencies = {}
        all_tasks = set()

        for task in tasks:
            task_name = task.get("name", "Unnamed Task")
            run_after = task.get("runAfter", [])
            all_tasks.add(task_name)

            if not run_after:
                markdown_content += f'"Start" --> {task_name}\n'
            else:
                for dependency in run_after:
                    task_dependencies.setdefault(dependency, []).append(task_name)

        for task, dependencies in task_dependencies.items():
            for dependency in dependencies:
                markdown_content += f'"{task}" --> {dependency}\n'

        end_tasks = all_tasks - set(task_dependencies.keys())
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

    def visualize_step_template(self, template):
        if not template:
            return ""
        markdown_content = "## Step template\n\n"

        if template.get("env", []):
            markdown_content += self.table_with_header(
                "**Environment Variables:**", ["Name", "Value"]
            )
            for var in template.get("env", []):
                name = var.get("name", "Unnamed Variable")
                value = var.get("value", "")
                if value:
                    markdown_content += f"| `{name}` | `{value}` |\n"

        if template.get("envFrom", []):
            markdown_content += self.table_with_header(
                "**Environment from config:**", ["Name", "Type"]
            )
            for value_from in template.get("envFrom"):
                if value_from.get("configMapRef", {}):
                    cm_name = value_from.get("configMapRef").get(
                        "name", "Not specified"
                    )
                    markdown_content += f"| `{cm_name}` | ConfigMap |\n"
                if value_from.get("secretRef", {}):
                    secret_name = value_from.get("secretRef").get(
                        "name", "Not specified"
                    )
                    markdown_content += f"| `{secret_name}` | Secret |\n"

        markdown_content += "\n"
        return markdown_content

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
            markdown_content += (
                f"| `{name}` | `{param_type}` | {description} | "
                f"{f'`{default}`' if default else ''} |\n"
            )
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
            markdown_content += f"| `{name}` | {description} | {optional} |\n"
        return markdown_content + "\n"

    def visualize_tasks(self, tasks):
        markdown_content = "## Tasks\n\n"
        for task in tasks:
            task_name = task.get("name", "Unnamed Task")
            markdown_content += f"### {task_name}\n\n"

            task_ref = task.get("taskRef", {})
            ref_name = task_ref.get("name", "Not specified")
            markdown_content += self.render_resource_reference(
                label="Task Reference",
                ref_name=ref_name,
                resource_paths=self.task_paths,
            )

            step_ref = task.get("ref", {})
            if step_ref:
                ref_name = step_ref.get("name", "Not specified")
                markdown_content += self.render_resource_reference(
                    label="StepAction Reference",
                    ref_name=ref_name,
                    resource_paths=self.stepaction_paths,
                )

            markdown_content += self.visualize_common_elements(task)

            if task.get("params"):
                markdown_content += self.table_with_header(
                    "**Parameters:**", ["Name", "Value"]
                )
                for param in task["params"]:
                    p_name = param.get("name", "Unnamed")
                    p_value = param.get("value", "")
                    if isinstance(p_value, list):
                        if not p_value:
                            p_value = '"<ul><li></li></ul>"'
                        else:
                            p_value = "<ul>" + "".join(
                                f"<li>`{item}`</li>" for item in p_value
                            ) + "</ul>"
                    else:
                        p_value = f"`{p_value}`"
                    markdown_content += f"| `{p_name}` | {p_value} |\n"
                markdown_content += "\n"

            if task.get("workspaces"):
                markdown_content += self.table_with_header(
                    "**Workspaces:**", ["Name", "Workspace", "Optional"]
                )
                for ws in task["workspaces"]:
                    ws_name = ws.get("name", "Unnamed Workspace")
                    ws_workspace = ws.get("workspace", "Not specified")
                    ws_optional = ws.get("optional", False)
                    markdown_content += (
                        f"| `{ws_name}` | `{ws_workspace}` | {ws_optional} |\n"
                    )
                markdown_content += "\n"

        return markdown_content

    def visualize_steps(self, steps):
        markdown_content = "## Steps\n\n"
        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"Step {i}")
            markdown_content += f"### {step_name}\n\n"
            markdown_content += self.visualize_common_elements(step)

            step_ref = step.get("ref", {})
            if step_ref:
                ref_name = step_ref.get("name", "Not specified")
                markdown_content += self.render_resource_reference(
                    label="StepAction Reference",
                    ref_name=ref_name,
                    resource_paths=self.stepaction_paths,
                )
            else:
                image = step.get("image", "Not specified")
                markdown_content += f"**Image:** `{image}`\n\n"
                markdown_content += self.render_script(step.get("script", ""))
                markdown_content += self.render_command(step.get("command", []))
                markdown_content += self.render_args(step.get("args", []))

            markdown_content += self.visualize_environment(step.get("env", []))
        return markdown_content

    def visualize_common_elements(self, spec):
        markdown_content = ""
        timeout = spec.get("timeout")
        if timeout:
            markdown_content += f"**Timeout:** `{timeout}`\n\n"

        when = spec.get("when", [])
        if when:
            markdown_content += "**When Expressions:**\n\n"
            for condition in when:
                input_value = condition.get("input", "")
                operator = condition.get("operator", "")
                values = condition.get("values", [])
                markdown_content += (
                    f"- Input: `{input_value}`, Operator: `{operator}`, "
                    f"Values: `{', '.join(values)}`\n"
                )
            markdown_content += "\n"

        retries = spec.get("retries")
        if retries:
            markdown_content += f"**Retries:** `{retries}`\n\n"
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
                markdown_content += (
                    f"| `{name}` | `{cm_name}:{cm_key}` | ConfigMap Reference | "
                    f"{optional} |\n"
                )
            elif "fieldRef" in value_from:
                field_path = value_from["fieldRef"].get("fieldPath", "Not specified")
                markdown_content += (
                    f"| `{name}` | `{field_path}` | Field Reference | |\n"
                )
            elif "secretKeyRef" in value_from:
                secret_name = value_from["secretKeyRef"].get("name", "Not specified")
                secret_key = value_from["secretKeyRef"].get("key", "Not specified")
                optional = value_from["secretKeyRef"].get("optional", False)
                markdown_content += (
                    f"| `{name}` | `{secret_name}:{secret_key}` | Secret Reference | "
                    f"{optional} |\n"
                )
            else:
                markdown_content += f"| `{name}` | Not specified | Unknown |\n"
        markdown_content += "\n"
        return markdown_content

    def visualize_usage(self, metadata, spec, kind="task"):
        resource_name = metadata.get("name", "Unnamed")
        display_name = metadata.get("annotations", {}).get(
            "tekton.dev/displayName", resource_name
        )

        params = [
            {"name": param["name"], "value": "<VALUE>"}
            for param in spec.get("params", [])
            if "default" not in param
        ]
        workspaces = [
            {"name": ws["name"], "workspace": "<WORKSPACE_NAME>"}
            for ws in spec.get("workspaces", [])
            if not ws.get("optional", False)
        ]

        if kind == "pipeline":
            usage_yaml = {
                "apiVersion": "tekton.dev/v1beta1",
                "kind": "PipelineRun",
                "metadata": {"generateName": f"{resource_name}-run-"},
                "spec": {
                    "pipelineRef": {"name": resource_name},
                    "params": params,
                    "workspaces": workspaces,
                },
            }
        else:
            usage_yaml = {
                "name": display_name,
                "taskRef": {"name": resource_name},
                "runAfter": ["<TASK_NAME>"],
                "params": params,
                "workspaces": workspaces,
            }

        if (
            not usage_yaml.get("spec", {}).get("workspaces", [])
            and not usage_yaml.get("workspaces", [])
        ):
            if "spec" in usage_yaml and "workspaces" in usage_yaml["spec"]:
                del usage_yaml["spec"]["workspaces"]
            elif "workspaces" in usage_yaml:
                del usage_yaml["workspaces"]

        if (
            not usage_yaml.get("spec", {}).get("params", [])
            and not usage_yaml.get("params", [])
        ):
            if "spec" in usage_yaml and "params" in usage_yaml["spec"]:
                del usage_yaml["spec"]["params"]
            elif "params" in usage_yaml:
                del usage_yaml["params"]

        yaml_str = yaml.dump([usage_yaml], default_flow_style=False)
        usage = "\n".join("    " + line for line in yaml_str.splitlines())
        content = f"""
## Usage

This is the minimum configuration required to use the `{resource_name}` {kind} in your project.

```yaml
{usage}
```
"""
        if self.include_cli_usage:
            content += self.generate_cli_command(metadata, spec, kind)

        content += f"""
Placeholders should be replaced with the appropriate values for your specific use case. Refer to the {kind}'s documentation for more details on the available parameters and workspaces.
"""
        if kind == "task":
            content += "The `runAfter` parameter is optional and only needed if you want to specify task dependencies for flow control.\n"

        content += "\n"
        return content

    def generate_cli_command(self, metadata, spec, kind="task"):
        name = metadata.get("name", "unnamed")
        cmd = f"tkn {kind} start {name}"

        for param in spec.get("params", []):
            p_name = param.get("name")
            if "default" in param:
                continue
            cmd += f" \\\n  -p {p_name}=<{p_name.upper()}>"

        for ws in spec.get("workspaces", []):
            if ws.get("optional", False):
                continue
            w_name = ws.get("name")
            cmd += f" \\\n  -w {w_name}=<{w_name.upper()}>"

        return f"\n**CLI:**\n\n```bash\n{cmd}\n```\n"

    def format_value(self, value):
        return format_value(value)

    def table_with_header(self, header, table_headers):
        return table_with_header(header, table_headers)

    def render_script(self, script):
        return render_script(script)

    def render_command(self, command):
        return render_command(command)

    def render_args(self, args):
        return render_args(args)

    def render_resource_reference(self, label, ref_name, resource_paths):
        return render_resource_reference(
            label=label,
            ref_name=ref_name,
            resource_paths=resource_paths,
            from_path=self.source_path,
            relative_path_fn=self.relative_path_fn,
        )

    def detect_script_type(self, script):
        return get_script_type(script)
