from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from html import escape
from logging import Logger
from typing import Any

import markdown
import yaml

from .rendering_utils import (
    code_value,
    format_value,
    get_script_type,
    render_args,
    render_command,
    render_resource_reference,
    render_script,
    resource_anchor,
    table_with_header,
    task_dependencies,
)


class MarkdownRenderer:
    def __init__(
        self,
        logger: Logger,
        plantuml_graphs: bool,
        plantuml_graph_direction: str,
        plantuml_theme: str,
        include_cli_usage: bool,
        task_paths: dict[str, dict[str, str]],
        stepaction_paths: dict[str, dict[str, str]],
        relative_path_fn: Callable[[str, str], str],
        source_path: str,
        include_usage: bool = True,
    ) -> None:
        self.logger = logger
        self.plantuml_graphs = plantuml_graphs
        self.plantuml_graph_direction = plantuml_graph_direction
        self.plantuml_theme = plantuml_theme
        self.include_usage = include_usage
        self.include_cli_usage = include_cli_usage
        self.task_paths = task_paths
        self.stepaction_paths = stepaction_paths
        self.relative_path_fn = relative_path_fn
        self.source_path = source_path

    def generate_markdown_content(self, resources: Sequence[Mapping[str, Any]]) -> str:
        self.logger.debug(
            "Generating Markdown content for %d resources", len(resources)
        )
        markdown_content = ""
        for resource in resources:
            kind = resource.get("kind", "")
            metadata = resource.get("metadata", {})
            spec = resource.get("spec", {})
            resource_name = metadata.get("name", "Unnamed Resource")
            self.resource_name = resource_anchor(resource)
            resource_version = metadata.get("labels", {}).get(
                "app.kubernetes.io/version", ""
            )
            if resource_version:
                resource_version = f" v{resource_version}"

            markdown_content += f'<a id="{resource_anchor(resource)}"></a>\n\n'
            markdown_content += f"# {kind}: {resource_name}{resource_version}\n\n"
            display_name = spec.get("displayName") or metadata.get(
                "annotations", {}
            ).get("tekton.dev/displayName")
            if display_name:
                markdown_content += f"**{self.format_value(display_name)}**\n\n"
            if kind.lower() == "pipeline":
                markdown_content += self.visualize_pipeline(spec)
                if self.include_usage:
                    markdown_content += self.visualize_example_invocation(
                        metadata, spec, "pipeline"
                    )
            elif kind.lower() == "task":
                markdown_content += self.visualize_task(metadata, spec)
            elif kind.lower() == "stepaction":
                markdown_content += self.visualize_stepaction(metadata, spec)

            source = escape(yaml.safe_dump(dict(resource), sort_keys=False))
            markdown_content += f"\n<details><summary>Resource definition</summary><pre><code>{source}</code></pre></details>\n\n---\n\n"
        return markdown_content

    def visualize_pipeline(self, spec: Mapping[str, Any]) -> str:
        self.logger.debug("Visualizing pipeline")
        markdown_content = self.description(spec)
        tasks = spec.get("tasks", [])
        final = spec.get("finally", [])
        markdown_content += f"**{len(tasks)} tasks** · **{len(final)} final tasks** · **{len(spec.get('params', []))} parameters**\n\n"
        markdown_content += "## Execution flow\n\nTasks without dependencies may run in parallel. Conditions can skip tasks.\n\n"
        if self.plantuml_graphs:
            markdown_content += self.make_graph_from_tasks(tasks, final)
        markdown_content += self.task_overview(tasks, final)
        markdown_content += self.visualize_parameters(spec.get("params", []))
        markdown_content += self.visualize_workspaces(spec.get("workspaces", []))
        markdown_content += self.visualize_results(spec.get("results", []))
        markdown_content += self.visualize_tasks(tasks)
        if final:
            markdown_content += self.visualize_tasks(final, "Finally")
        return markdown_content

    def visualize_task(
        self, metadata: Mapping[str, Any], spec: Mapping[str, Any]
    ) -> str:
        self.logger.debug("Visualizing task: %s", metadata.get("name", "Unnamed Task"))
        markdown_content = self.description(spec)
        steps = spec.get("steps", [])
        markdown_content += self.visualize_step_overview(steps)
        markdown_content += self.visualize_parameters(spec.get("params", []))
        markdown_content += self.visualize_workspaces(spec.get("workspaces", []))
        markdown_content += self.visualize_results(spec.get("results", []))
        markdown_content += self.visualize_step_template(spec.get("stepTemplate", {}))
        markdown_content += self.visualize_step_details(steps)
        if self.include_usage:
            markdown_content += self.visualize_example_invocation(metadata, spec)
        return markdown_content

    def visualize_stepaction(
        self, metadata: Mapping[str, Any], spec: Mapping[str, Any]
    ) -> str:
        self.logger.debug(
            "Visualizing stepaction: %s", metadata.get("name", "Unnamed StepAction")
        )
        markdown_content = self.description(spec)
        markdown_content += "## Execution overview\n\n"
        image = spec.get("image", "Not specified")
        markdown_content += f"**Image:** {code_value(image)}\n\n"
        markdown_content += self.visualize_parameters(spec.get("params", []))
        markdown_content += self.visualize_results(spec.get("results", []))
        markdown_content += "## Implementation\n\n"

        markdown_content += self.render_script(spec.get("script", ""))
        markdown_content += self.render_command(spec.get("command", []))
        markdown_content += self.render_args(spec.get("args", []))
        markdown_content += self.visualize_environment(spec.get("env", []))
        return markdown_content

    def make_graph_from_tasks(
        self, tasks: Sequence[Mapping[str, Any]], final: Sequence[Mapping[str, Any]]
    ) -> str:
        self.logger.debug(
            "Generating graph from %d tasks and %d final tasks", len(tasks), len(final)
        )
        markdown_content = (
            f"```plantuml\n@startuml\n{self.plantuml_graph_direction}\n"
            f"!theme {self.plantuml_theme}\n"
            "skinparam shadowing false\n"
            "skinparam rectangleRoundCorner 12\n"
            'rectangle "Start" as pipeline_start\n'
        )

        aliases = {task["name"]: f"task_{i}" for i, task in enumerate(tasks)}
        dependencies_by_task = {task["name"]: task_dependencies(task) for task in tasks}
        for task in tasks:
            name = task["name"]
            label = name + (" (conditional)" if task.get("when") else "")
            markdown_content += f'rectangle "{label}" as {aliases[name]}\n'
        for task in tasks:
            dependencies = dependencies_by_task[task["name"]]
            if not dependencies:
                markdown_content += f"pipeline_start --> {aliases[task['name']]}\n"
            for dependency in dependencies:
                if dependency in aliases:
                    markdown_content += (
                        f"{aliases[dependency]} --> {aliases[task['name']]}\n"
                    )
        if final:
            markdown_content += (
                'rectangle "Finally\\nAfter all tasks settle" as final_phase\n'
            )
            # Only connect branch endpoints to the phase boundary. Earlier tasks
            # already reach it through their dependents; extra edges obscure the DAG.
            predecessors = {
                dependency
                for dependencies in dependencies_by_task.values()
                for dependency in dependencies
            }
            for name, alias in aliases.items():
                if name not in predecessors:
                    markdown_content += f"{alias} ..> final_phase\n"
            if not tasks:
                markdown_content += "pipeline_start --> final_phase\n"
            for i, task in enumerate(final):
                markdown_content += f'rectangle "{task["name"]}" as final_{i}\nfinal_phase --> final_{i}\n'

        markdown_content += "@enduml\n```\n"
        return markdown_content

    def description(self, spec: Mapping[str, Any]) -> str:
        return (
            str(spec.get("description") or "No description provided.").strip() + "\n\n"
        )

    def task_overview(
        self, tasks: Sequence[Mapping[str, Any]], final: Sequence[Mapping[str, Any]]
    ) -> str:
        if not tasks and not final:
            return "No tasks declared.\n\n"
        content = self.table_with_header(
            "", ["Task", "Uses", "Runs after", "Execution"]
        )
        for phase, entries in (("Tasks", tasks), ("Finally", final)):
            for task in entries:
                name = task["name"]
                ref = task.get("taskRef", {})
                uses = ref.get("name") or (
                    "Resolver: " + ref["resolver"]
                    if ref.get("resolver")
                    else "Inline task"
                )
                if ref.get("name") in self.task_paths and not ref.get("resolver"):
                    path = self.relative_path_fn(
                        self.source_path, self.task_paths[ref["name"]]["path"]
                    )
                    uses = f"[{code_value(uses)}]({path})"
                else:
                    uses = code_value(uses)
                after = ", ".join(task_dependencies(task)) or "Start"
                if phase == "Finally":
                    after = "All tasks settled"
                execution = "Conditional" if task.get("when") else "Always eligible"
                content += f"| [{code_value(name)}](#{self.task_anchor(name, phase)}) | {uses} | {self.format_value(after)} | {execution} |\n"
        return content + "\n"

    def task_anchor(self, name: str, phase: str) -> str:
        key = (
            self.source_path
            + ":"
            + getattr(self, "resource_name", "")
            + ":"
            + phase
            + ":"
            + name
        )
        return "task-" + sha256(key.encode()).hexdigest()[:12]

    def visualize_step_template(self, template: Mapping[str, Any]) -> str:
        if not template:
            return ""
        markdown_content = "## Step template\n\n"

        if template.get("image"):
            markdown_content += (
                f"**Default image:** {code_value(template['image'])}\n\n"
            )
        markdown_content += self.visualize_common_elements(template)
        markdown_content += self.render_command(template.get("command", []))
        markdown_content += self.render_args(template.get("args", []))
        markdown_content += self.visualize_environment(template.get("env", []))

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

    def visualize_parameters(self, params: Sequence[Mapping[str, Any]]) -> str:
        if not params:
            return "## Parameters\n\nNo parameters\n"
        markdown_content = self.table_with_header(
            "## Parameters", ["Name", "Type", "Required", "Description", "Default"]
        )
        for param in params:
            name = param.get("name", "Unnamed Parameter")
            param_type = param.get("type", "string")
            description = self.format_value(
                param.get("description", "No description provided.")
            )
            default = code_value(param["default"]) if "default" in param else "—"
            required = "No" if "default" in param else "Yes"
            markdown_content += f"| {code_value(name)} | {code_value(param_type)} | {required} | {description} | {default} |\n"
        return markdown_content + "\n"

    def visualize_workspaces(self, workspaces: Sequence[Mapping[str, Any]]) -> str:
        if not workspaces:
            return ""
        markdown_content = self.table_with_header(
            "## Workspaces", ["Name", "Description", "Optional"]
        )
        for workspace in workspaces:
            name = workspace.get("name", "Unnamed Workspace")
            description = self.format_value(workspace.get("description", ""))
            optional = workspace.get("optional", False)
            markdown_content += f"| {code_value(name)} | {description} | {'Yes' if optional else 'No'} |\n"
        return markdown_content + "\n"

    def visualize_tasks(
        self, tasks: Sequence[Mapping[str, Any]], title: str = "Tasks"
    ) -> str:
        markdown_content = f"## {title}\n\n"
        if title == "Finally":
            markdown_content += "Final tasks run after the main tasks settle, including failures. They run in parallel; conditions or missing results may skip them.\n\n"
        for task in tasks:
            task_name = task.get("name", "Unnamed Task")
            markdown_content += f'<a id="{self.task_anchor(task_name, title)}"></a>\n\n### {task_name}\n\n'
            if task.get("displayName"):
                markdown_content += f"**{self.format_value(task['displayName'])}**\n\n"

            task_ref = task.get("taskRef", {})
            ref_name = task_ref.get("name", "Not specified")
            if task_ref.get("resolver"):
                markdown_content += f"**Remote resolver:** {code_value(task_ref['resolver'])}\n\n```yaml\n{yaml.safe_dump(task_ref, sort_keys=False)}```\n\n"
            elif "taskSpec" in task:
                markdown_content += "**Inline task**\n\n"
                markdown_content += f"```yaml\n{yaml.safe_dump(task['taskSpec'], sort_keys=False)}```\n\n"
            else:
                markdown_content += self.render_resource_reference(
                    label="Task Reference",
                    ref_name=ref_name,
                    resource_paths=self.task_paths,
                )
            dependencies = task_dependencies(task)
            if dependencies:
                markdown_content += (
                    "**Runs after:** "
                    + ", ".join(code_value(d) for d in dependencies)
                    + "\n\n"
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
                    "**Parameter bindings:**", ["Task parameter", "Supplied value"]
                )
                for param in task["params"]:
                    p_name = param.get("name", "Unnamed")
                    p_value = param.get("value", "")
                    p_value = code_value(p_value)
                    markdown_content += f"| `{p_name}` | {p_value} |\n"
                markdown_content += "\n"

            if task.get("workspaces"):
                markdown_content += self.table_with_header(
                    "**Workspace bindings:**",
                    ["Task workspace", "Pipeline workspace", "Subpath"],
                )
                for ws in task["workspaces"]:
                    ws_name = ws.get("name", "Unnamed Workspace")
                    ws_workspace = ws.get("workspace", "Not specified")
                    ws_subpath = code_value(ws["subPath"]) if "subPath" in ws else "—"
                    markdown_content += (
                        f"| `{ws_name}` | `{ws_workspace}` | {ws_subpath} |\n"
                    )
                markdown_content += "\n"

        return markdown_content

    def visualize_steps(self, steps: Sequence[Mapping[str, Any]]) -> str:
        return self.visualize_step_overview(steps) + self.visualize_step_details(steps)

    def visualize_step_overview(self, steps: Sequence[Mapping[str, Any]]) -> str:
        markdown_content = "## Step overview\n\nSteps run in the order shown.\n\n"
        if steps:
            markdown_content += self.table_with_header(
                "", ["Order", "Step", "Image or StepAction"]
            )
            for i, step in enumerate(steps, 1):
                name = step.get("name", f"Step {i}")
                uses = step.get("ref", {}).get("name") or step.get(
                    "image", "Inherited from step template"
                )
                markdown_content += f"| {i} | [{code_value(name)}](#{self.task_anchor(name, 'Steps')}) | {code_value(uses)} |\n"
            markdown_content += "\n"
        return markdown_content

    def visualize_step_details(self, steps: Sequence[Mapping[str, Any]]) -> str:
        if not steps:
            return ""
        markdown_content = "## Step details\n\n"
        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"Step {i}")
            markdown_content += f'<a id="{self.task_anchor(step_name, "Steps")}"></a>\n\n### {step_name}\n\n'
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

            if step.get("params"):
                markdown_content += self.table_with_header(
                    "**Parameter bindings:**",
                    ["StepAction parameter", "Supplied value"],
                )
                for param in step["params"]:
                    markdown_content += f"| {code_value(param['name'])} | {code_value(param.get('value', ''))} |\n"
                markdown_content += "\n"
            markdown_content += self.visualize_environment(step.get("env", []))
        return markdown_content

    def visualize_common_elements(self, spec: Mapping[str, Any]) -> str:
        markdown_content = ""
        for field, label in (
            ("workingDir", "Working directory"),
            ("onError", "On error"),
        ):
            if field in spec:
                markdown_content += f"**{label}:** {code_value(spec[field])}\n\n"
        timeout = spec.get("timeout")
        if timeout:
            markdown_content += f"**Timeout:** `{timeout}`\n\n"

        when = spec.get("when", [])
        if when:
            markdown_content += "**When Expressions:**\n\n"
            for condition in when:
                if "cel" in condition:
                    markdown_content += f"- CEL: {code_value(condition['cel'])}\n"
                    continue
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

    def visualize_results(self, results: Sequence[Mapping[str, Any]]) -> str:
        if not results:
            return "\n"
        markdown_content = self.table_with_header(
            "## Results", ["Name", "Type", "Description", "Value expression"]
        )
        for result in results:
            name = result.get("name", "Unnamed Result")
            description = result.get("description", "No description provided.")
            markdown_content += f"| {code_value(name)} | {code_value(result.get('type', 'string'))} | {self.format_value(description)} | {code_value(result['value']) if 'value' in result else 'Produced by steps'} |\n"
        return markdown_content + "\n"

    def visualize_environment(self, env: Sequence[Mapping[str, Any]]) -> str:
        if not env:
            return ""
        markdown_content = self.table_with_header(
            "**Environment Variables:**", ["Name", "Value", "Source", "Optional"]
        )
        for var in env:
            name = var.get("name", "Unnamed Variable")
            value = var.get("value", "")
            value_from = var.get("valueFrom", {})

            if "value" in var:
                markdown_content += (
                    f"| {code_value(name)} | {code_value(value)} | Literal | — |\n"
                )
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
                markdown_content += f"| `{name}` | Not specified | Unknown | — |\n"
        markdown_content += "\n"
        return markdown_content

    def visualize_example_invocation(
        self,
        metadata: Mapping[str, Any],
        spec: Mapping[str, Any],
        kind: str = "task",
    ) -> str:
        # Render the disclosure body explicitly so it works without requiring
        # TechDocs sites to enable Markdown parsing inside HTML blocks.
        body = self.visualize_usage(metadata, spec, kind).replace("## Usage\n", "", 1)
        html = markdown.markdown(body, extensions=["fenced_code"])
        return (
            "\n<details><summary>Example invocation</summary>\n"
            + html
            + "\n</details>\n\n"
        )

    def visualize_usage(
        self,
        metadata: Mapping[str, Any],
        spec: Mapping[str, Any],
        kind: str = "task",
    ) -> str:
        resource_name = metadata.get("name", "Unnamed")

        params = [
            {
                "name": param["name"],
                "value": []
                if param.get("type") == "array"
                else {}
                if param.get("type") == "object"
                else "<VALUE>",
            }
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
                "apiVersion": "tekton.dev/v1",
                "kind": "PipelineRun",
                "metadata": {"generateName": f"{resource_name}-run-"},
                "spec": {
                    "pipelineRef": {"name": resource_name},
                    "params": params,
                    "workspaces": [
                        {
                            "name": ws["name"],
                            "persistentVolumeClaim": {"claimName": "<PVC_NAME>"},
                        }
                        for ws in workspaces
                    ],
                },
            }
        else:
            usage_yaml = {
                "name": resource_name,
                "taskRef": {"name": resource_name},
                "params": params,
                "workspaces": workspaces,
            }

        if not usage_yaml.get("spec", {}).get("workspaces", []) and not usage_yaml.get(
            "workspaces", []
        ):
            if "spec" in usage_yaml and "workspaces" in usage_yaml["spec"]:
                del usage_yaml["spec"]["workspaces"]
            elif "workspaces" in usage_yaml:
                del usage_yaml["workspaces"]

        if not usage_yaml.get("spec", {}).get("params", []) and not usage_yaml.get(
            "params", []
        ):
            if "spec" in usage_yaml and "params" in usage_yaml["spec"]:
                del usage_yaml["spec"]["params"]
            elif "params" in usage_yaml:
                del usage_yaml["params"]

        yaml_str = yaml.safe_dump(
            usage_yaml if kind == "pipeline" else [usage_yaml], sort_keys=False
        )
        usage = yaml_str.rstrip()
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

    def generate_cli_command(
        self, metadata: Mapping[str, Any], spec: Mapping[str, Any], kind: str = "task"
    ) -> str:
        name = metadata.get("name", "unnamed")
        cmd = f"tkn {kind} start {name}"

        for param in spec.get("params", []):
            p_name = param.get("name")
            if "default" in param:
                continue
            cmd += f" \\\n  -p '{p_name}=<{p_name.upper()}>'"

        for ws in spec.get("workspaces", []):
            if ws.get("optional", False):
                continue
            w_name = ws.get("name")
            cmd += f" \\\n  -w 'name={w_name},claimName=<PVC_NAME>'"

        return f"\n**CLI:**\n\n```bash\n{cmd}\n```\n"

    def format_value(self, value: Any) -> Any:
        return format_value(value)

    def table_with_header(self, header: str, table_headers: Sequence[str]) -> str:
        return table_with_header(header, table_headers)

    def render_script(self, script: str) -> str:
        return render_script(script)

    def render_command(self, command: Sequence[str]) -> str:
        return render_command(command)

    def render_args(self, args: Sequence[str]) -> str:
        return render_args(args)

    def render_resource_reference(
        self, label: str, ref_name: str, resource_paths: dict[str, dict[str, str]]
    ) -> str:
        return render_resource_reference(
            label=label,
            ref_name=ref_name,
            resource_paths=resource_paths,
            from_path=self.source_path,
            relative_path_fn=self.relative_path_fn,
        )

    def detect_script_type(self, script: str) -> str:
        return get_script_type(script)
