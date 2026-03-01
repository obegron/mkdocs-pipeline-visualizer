import os
import yaml
import logging
import hashlib
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files
from mkdocs.config import config_options
from .rendering_utils import (
    format_value,
    get_script_type,
    render_args,
    render_command,
    render_resource_reference,
    render_script,
    table_with_header,
)
from .navigation_utils import (
    add_to_nav,
    find_or_create_section,
    get_group,
    get_relative_path,
    remove_empty_sections,
    semantic_version_key,
)


class PipelineVisualizer(BasePlugin):

    config_scheme = (
        ("plantuml_graph_direction", config_options.Choice(["TB", "LR"], default="TB")),
        ("plantuml_theme", config_options.Type(str, default="_none_")),
        ("plantuml_graphs", config_options.Type(bool, default=True)),
        ("nav_generation", config_options.Type(bool, default=True)),
        ("nav_hide_empty_sections", config_options.Type(bool, default=False)),
        ("nav_section_pipelines", config_options.Type(str, default="Pipelines")),
        ("nav_section_tasks", config_options.Type(str, default="Tasks")),
        ("nav_section_stepactions", config_options.Type(str, default="StepActions")),
        ("nav_pipeline_grouping_offset", config_options.Type(str, default=None)),
        ("nav_task_grouping_offset", config_options.Type(str, default=None)),
        ("nav_stepaction_grouping_offset", config_options.Type(str, default=None)),
        ("nav_group_tasks_by_category", config_options.Type(bool, default=False)),
        ("nav_category_mapping", config_options.Type(dict, default={})),
        ("include_cli_usage", config_options.Type(bool, default=True)),
        (
            "log_level",
            config_options.Choice(
                ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO"
            ),
        ),
    )

    def __init__(self):
        self.logger = logging.getLogger("mkdocs.plugins.pipeline_visualizer")
        self._processed_files = {}
        self._task_paths = {}  # Store relative paths for tasks
        self._stepaction_paths = {}  # Store relative paths for stepactions
        self.in_serve_mode = False

    def on_config(self, config):
        self.nav_task_grouping_offset = self._parse_grouping_offset(
            self.config["nav_task_grouping_offset"]
        )
        self.nav_stepaction_grouping_offset = self._parse_grouping_offset(
            self.config["nav_stepaction_grouping_offset"]
        )
        self.logger.setLevel(getattr(logging, self.config["log_level"]))

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.propagate = False

        self.plantuml_graph_direction = (
            "left to right direction"
            if self.config["plantuml_graph_direction"] == "LR"
            else "top to bottom direction"
        )
        self.plantuml_theme = self.config["plantuml_theme"]
        self.plantuml_graphs = self.config["plantuml_graphs"]
        self.nav_generation = self.config["nav_generation"]
        self.nav_hide_empty_sections = self.config["nav_hide_empty_sections"]
        self.nav_section_pipelines = self.config["nav_section_pipelines"]
        self.nav_section_tasks = self.config["nav_section_tasks"]
        self.nav_section_stepactions = self.config["nav_section_stepactions"]
        self.nav_group_tasks_by_category = self.config["nav_group_tasks_by_category"]
        self.nav_pipeline_grouping_offset = self._parse_grouping_offset(
            self.config["nav_pipeline_grouping_offset"]
        )
        self.include_cli_usage = self.config["include_cli_usage"]
        self.logger.info(
            "PipelineVisualizer plugin initialized with configuration: %s", self.config
        )

    def _parse_grouping_offset(self, offset_str):
        if offset_str is None:
            return None
        try:
            start, end = map(int, offset_str.split(":"))
            if end > 0:
                self.logger.error(
                    "invalid value %s, start:end end must be 0 or less, Using default (None)",
                    offset_str,
                )
                return None
            if start < 0:
                self.logger.error(
                    "invalid value %s, start:end start must be atleast 0, Using default (None)",
                    offset_str,
                )
                return None
            return (start, end)
        except ValueError:
            self.logger.error(
                f"Invalid grouping offset format: {offset_str}. Using default (None)."
            )
            return None

    def on_files(self, files, config):
        pipeline_versions = {}
        task_versions = {}
        stepaction_versions = {}
        new_files = []

        # Process tasks and stepactions first to build task reference map
        for file in files:
            if not file.src_path.endswith(".yaml"):
                continue

            resources = self._load_yaml(file.abs_src_path)
            if resources and any(
                r.get("kind", "").lower() in ["task", "stepaction"] for r in resources
            ):
                new_file = self._process_yaml_file(
                    file, config, pipeline_versions, task_versions, stepaction_versions
                )
                if new_file:
                    new_files.append(new_file)

        # Then process pipelines with complete task reference map
        for file in files:
            if not file.src_path.endswith(".yaml"):
                continue

            resources = self._load_yaml(file.abs_src_path)
            if resources and any(
                r.get("kind", "").lower() == "pipeline" for r in resources
            ):
                new_file = self._process_yaml_file(
                    file, config, pipeline_versions, task_versions, stepaction_versions
                )
                if new_file:
                    new_files.append(new_file)

        if self.nav_generation:
            self._update_navigation(config["nav"], pipeline_versions, task_versions, stepaction_versions)

        return Files(list(files) + [f for f in new_files if f is not None])

    def _process_yaml_file(self, file, config, pipeline_versions, task_versions, stepaction_versions):
        """Process YAML file containing one or more resources"""
        resources = self._load_yaml(file.abs_src_path)
        if not resources:
            self.logger.warning("Failed to load YAML file: %s", file.abs_src_path)
            return None

        # Sort resources to ensure tasks are processed first
        resources.sort(key=lambda x: x.get("kind", "") != "Task")

        content = self._generate_markdown_content(resources, file.src_path)
        new_file = self._create_markdown_file(file, config, content)

        if new_file:
            for resource in resources:
                kind = resource.get("kind", "").lower()
                if kind in ["pipeline", "task", "stepaction"]:
                    self._add_to_versions(
                        resource, new_file, kind, pipeline_versions, task_versions, stepaction_versions
                    )

        return new_file

    def _load_yaml(self, file_path):
        """Load YAML file, supporting multiple documents"""
        try:
            with open(file_path, "r") as f:
                content = f.read().strip()
                if not content:
                    return None
                documents = list(yaml.safe_load_all(content))
                valid_docs = [doc for doc in documents if doc and isinstance(doc, dict)]
                return valid_docs if valid_docs else None
        except yaml.YAMLError as e:
            self.logger.error("Error parsing YAML file %s: %s", file_path, e)
            return None

    def _create_markdown_file(self, original_file, config, content, suffix=""):
        """Create markdown file with optional suffix for multi-doc files"""
        base_path = original_file.abs_src_path.replace(".yaml", f"{suffix}.md")
        os.makedirs(os.path.dirname(base_path), exist_ok=True)

        new_content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        # Check if file exists and content is the same
        if os.path.exists(base_path):
            with open(base_path, "r") as f:
                existing_content = f.read()
                existing_content_hash = hashlib.md5(
                    existing_content.encode("utf-8")
                ).hexdigest()
                if new_content_hash == existing_content_hash:
                    self.logger.debug(
                        "Skipping write for %s: content unchanged", base_path
                    )
                    # Even if content is unchanged, return the File object so it's included in navigation
                    return File(
                        original_file.src_path.replace(".yaml", f"{suffix}.md"),
                        original_file.src_dir,
                        original_file.dest_dir,
                        config["site_dir"],
                    )

        with open(base_path, "w") as f:
            f.write(content)

        self.logger.debug("Created Markdown file: %s", base_path)
        return File(
            original_file.src_path.replace(".yaml", f"{suffix}.md"),
            original_file.src_dir,
            original_file.dest_dir,
            config["site_dir"],
        )

    def _generate_markdown_content(self, resources, source_path):
        self.logger.debug(
            "Generating Markdown content for %d resources", len(resources)
        )
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
                markdown_content += self._visualize_pipeline(spec, source_path)
            elif kind.lower() == "task":
                markdown_content += self._visualize_task(metadata, spec, source_path)
            elif kind.lower() == "stepaction":
                markdown_content += self._visualize_stepaction(metadata, spec)

            markdown_content += "\n---\n\n"
        return markdown_content

    def _visualize_pipeline(self, spec, source_path):
        self.logger.debug("Visualizing pipeline")
        markdown_content = ""
        tasks = spec.get("tasks", [])
        final = spec.get("finally", [])
        if self.plantuml_graphs:
            markdown_content += self._make_graph_from_tasks(tasks, final)
        markdown_content += self._visualize_parameters(spec.get("params", []))
        markdown_content += self._visualize_workspaces(spec.get("workspaces", []))
        markdown_content += self._visualize_tasks(tasks, source_path)
        if final:
            markdown_content += "## Finally\n\n"
            markdown_content += self._visualize_tasks(final, source_path)
        return markdown_content

    def _visualize_task(self, metadata, spec, source_path):
        self.logger.debug("Visualizing task: %s", metadata.get("name", "Unnamed Task"))
        markdown_content = (
            f"## Description\n>{spec.get('description','No description')}\n"
        )
        markdown_content += self._visualize_parameters(spec.get("params", []))
        markdown_content += self._visualize_results(spec.get("results", []))
        markdown_content += self._visualize_workspaces(spec.get("workspaces", []))
        markdown_content += self._visualize_step_template(spec.get("stepTemplate", []))
        markdown_content += self._visualize_steps(spec.get("steps", []), source_path)
        markdown_content += self._visualize_usage(metadata, spec)
        return markdown_content

    def _visualize_stepaction(self, metadata, spec):
        self.logger.debug("Visualizing stepaction: %s", metadata.get("name", "Unnamed StepAction"))
        markdown_content = (
            f"## Description\n>{spec.get('description','No description')}\n"
        )
        markdown_content += self._visualize_parameters(spec.get("params", []))
        markdown_content += self._visualize_results(spec.get("results", []))

        image = spec.get("image", "Not specified")
        markdown_content += f"\n**Image:** `{image}`\n\n"

        script = spec.get("script", "")
        markdown_content += self._render_script(script)

        command = spec.get("command", [])
        markdown_content += self._render_command(command)

        args = spec.get("args", [])
        markdown_content += self._render_args(args)

        markdown_content += self._visualize_environment(spec.get("env", []))
        return markdown_content

    def _make_graph_from_tasks(self, tasks, final):
        self.logger.debug(
            "Generating graph from %d tasks and %d final tasks", len(tasks), len(final)
        )
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

    def _visualize_step_template(self, template):
        if not template:
            return ""
        markdown_content = "## Step template\n\n"

        if template.get("env", []):
            markdown_content += self._table_with_header(
                "**Environment Variables:**", ["Name", "Value"]
            )
            for var in template.get("env", []):
                name = var.get("name", "Unnamed Variable")
                value = var.get("value", "")
                if value:
                    markdown_content += f"| `{name}` | `{value}` |\n"

        if template.get("envFrom", []):
            markdown_content += self._table_with_header(
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

    def _visualize_parameters(self, params):
        if not params:
            return "## Parameters\n\nNo parameters\n"
        markdown_content = self._table_with_header(
            "## Parameters", ["Name", "Type", "Description", "Default"]
        )
        for param in params:
            name = param.get("name", "Unnamed Parameter")
            param_type = param.get("type", "String")
            description = self._format_value(
                param.get("description", "No description provided.")
            )
            default = param.get("default", "")
            markdown_content += f"| `{name}` | `{param_type}` | {description} | {f'`{default}`' if default else ''} |\n"
        return markdown_content + "\n"

    def _visualize_workspaces(self, workspaces):
        if not workspaces:
            return ""
        markdown_content = self._table_with_header(
            "## Workspaces", ["Name", "Description", "Optional"]
        )
        for workspace in workspaces:
            name = workspace.get("name", "Unnamed Workspace")
            description = self._format_value(workspace.get("description", ""))
            optional = workspace.get("optional", False)
            markdown_content += f"| `{name}` | {description} | { optional } |\n"
        return markdown_content + "\n"

    def _visualize_tasks(self, tasks, source_path):
        markdown_content = "## Tasks\n\n"
        for task in tasks:
            task_name = task.get("name", "Unnamed Task")
            markdown_content += f"### {task_name}\n\n"

            # Task Reference with relative link if available
            task_ref = task.get("taskRef", {})
            ref_name = task_ref.get("name", "Not specified")
            markdown_content += self._render_resource_reference(
                label="Task Reference",
                ref_name=ref_name,
                resource_paths=self._task_paths,
                source_path=source_path,
            )

            step_ref = task.get("ref", {})
            if step_ref:
                ref_name = step_ref.get("name", "Not specified")
                markdown_content += self._render_resource_reference(
                    label="StepAction Reference",
                    ref_name=ref_name,
                    resource_paths=self._stepaction_paths,
                    source_path=source_path,
                )
            
            markdown_content += self._visualize_common_elements(task)

            # List parameters passed with default values
            if task.get("params"):
                markdown_content += self._table_with_header("**Parameters:**", ["Name", "Value"])
                for param in task["params"]:
                    p_name = param.get("name", "Unnamed")
                    p_value = param.get("value", "")
                    if isinstance(p_value, list):
                        if not p_value:
                            p_value = '"<ul><li></li></ul>"'
                        else:
                            p_value = "<ul>" + "".join(f"<li>`{item}`</li>" for item in p_value) + "</ul>"
                    else:
                        p_value = f"`{p_value}`"
                    markdown_content += f"| `{p_name}` | {p_value} |\n"
                markdown_content += "\n"

            if task.get("workspaces"):
                markdown_content += self._table_with_header("**Workspaces:**", ["Name", "Workspace", "Optional"])
                for ws in task["workspaces"]:
                    ws_name = ws.get("name", "Unnamed Workspace")
                    ws_workspace = ws.get("workspace", "Not specified")
                    ws_optional = ws.get("optional", False)
                    markdown_content += f"| `{ws_name}` | `{ws_workspace}` | {ws_optional} |\n"
                markdown_content += "\n"
            
        return markdown_content

    def _visualize_steps(self, steps, source_path):
        markdown_content = "## Steps\n\n"
        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"Step {i}")
            markdown_content += f"### {step_name}\n\n"
            markdown_content += self._visualize_common_elements(step)

            # StepAction Reference
            step_ref = step.get("ref", {})
            if step_ref:
                ref_name = step_ref.get("name", "Not specified")
                markdown_content += self._render_resource_reference(
                    label="StepAction Reference",
                    ref_name=ref_name,
                    resource_paths=self._stepaction_paths,
                    source_path=source_path,
                )
            else:
                # Image
                image = step.get("image", "Not specified")
                markdown_content += f"**Image:** `{image}`\n\n"

                # Script
                script = step.get("script", "")
                markdown_content += self._render_script(script)

                # Command
                command = step.get("command", [])
                markdown_content += self._render_command(command)

                # Args
                args = step.get("args", [])
                markdown_content += self._render_args(args)

            # Environment Variables
            markdown_content += self._visualize_environment(step.get("env", []))
        return markdown_content

    def _visualize_common_elements(self, spec):
        markdown_content = ""

        # Timeout
        timeout = spec.get("timeout")
        if timeout:
            markdown_content += f"**Timeout:** `{timeout}`\n\n"

        # When
        when = spec.get("when", [])
        if when:
            markdown_content += "**When Expressions:**\n\n"
            for condition in when:
                input = condition.get("input", "")
                operator = condition.get("operator", "")
                values = condition.get("values", [])
                markdown_content += f"- Input: `{input}`, Operator: `{operator}`, Values: `{', '.join(values)}`\n"
            markdown_content += "\n"

        # Retries
        retries = spec.get("retries")
        if retries:
            markdown_content += f"**Retries:** `{retries}`\n\n"

        return markdown_content

    def _visualize_results(self, results):
        if not results:
            return "\n"
        markdown_content = self._table_with_header(
            "## Results", ["Name", "Description"]
        )
        for result in results:
            name = result.get("name", "Unnamed Result")
            description = result.get("description", "No description provided.")
            markdown_content += f"| `{name}` | {description} |\n"
        return markdown_content + "\n"

    def _visualize_environment(self, env):
        if not env:
            return ""
        markdown_content = self._table_with_header(
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

    def _visualize_usage(self, metadata, spec, kind="task"):
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
                "metadata": {
                    "generateName": f"{resource_name}-run-"
                },
                "spec": {
                    "pipelineRef": {
                        "name": resource_name
                    },
                    "params": params,
                    "workspaces": workspaces
                }
            }
        else:
            # Default to Task usage (TaskRun or Pipeline task)
            usage_yaml = {
                "name": display_name,
                "taskRef": {"name": resource_name},
                "runAfter": ["<TASK_NAME>"],
                "params": params,
                "workspaces": workspaces,
            }

        if not usage_yaml.get("spec", {}).get("workspaces", []) and not usage_yaml.get("workspaces", []):
             if "spec" in usage_yaml and "workspaces" in usage_yaml["spec"]:
                 del usage_yaml["spec"]["workspaces"]
             elif "workspaces" in usage_yaml:
                 del usage_yaml["workspaces"]

        if not usage_yaml.get("spec", {}).get("params", []) and not usage_yaml.get("params", []):
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
            content += self._generate_cli_command(metadata, spec, kind)

        content += f"""
Placeholders should be replaced with the appropriate values for your specific use case. Refer to the {kind}'s documentation for more details on the available parameters and workspaces.
"""
        if kind == "task":
            content += "The `runAfter` parameter is optional and only needed if you want to specify task dependencies for flow control.\n"
            
        content += "\n"
        return content

    def _generate_cli_command(self, metadata, spec, kind="task"):
        name = metadata.get("name", "unnamed")
        
        cmd = f"tkn {kind} start {name}"
        
        # Params
        params = spec.get("params", [])
        for param in params:
            p_name = param.get("name")
            if "default" in param:
                continue 
            
            cmd += f" \\\n  -p {p_name}=<{p_name.upper()}>"

        # Workspaces
        workspaces = spec.get("workspaces", [])
        for ws in workspaces:
            if ws.get("optional", False):
                continue
            w_name = ws.get("name")
            cmd += f" \\\n  -w {w_name}=<{w_name.upper()}>"
            
        return f"\n**CLI:**\n\n```bash\n{cmd}\n```\n"

    def _format_value(self, value):
        return format_value(value)

    def _table_with_header(self, header, table_headers):
        return table_with_header(header, table_headers)

    def _render_script(self, script):
        return render_script(script)

    def _render_command(self, command):
        return render_command(command)

    def _render_args(self, args):
        return render_args(args)

    def _render_resource_reference(self, label, ref_name, resource_paths, source_path):
        return render_resource_reference(
            label=label,
            ref_name=ref_name,
            resource_paths=resource_paths,
            from_path=source_path,
            relative_path_fn=self._get_relative_path,
        )

    def _get_script_type(self, script):
        return get_script_type(script)

    def _get_task_categories(self, metadata):
        """Extract categories from task metadata"""
        if metadata and "annotations" in metadata:
            categories = metadata["annotations"].get("tekton.dev/categories", "")
            return [c.strip() for c in categories.split(",")] if categories else []
        return []

    def _add_to_versions(self, resource, file, kind, pipeline_versions, task_versions, stepaction_versions):
        metadata = resource.get("metadata", {})
        name = metadata.get("name", "Unnamed Resource")
        version_label = metadata.get("labels", {}).get("app.kubernetes.io/version", "")
        version_str = version_label
        path = file.src_path.replace("\\", "/")

        if kind == "task":
            # Store task reference with version comparison
            current_version = self._task_paths.get(name, {}).get("version", "")
            if not current_version or self._semantic_version_key(
                version_label
            ) > self._semantic_version_key(current_version):
                self._task_paths[name] = {"version": version_label, "path": path}

            # Add to task versions
            categories = (
                metadata.get("annotations", {})
                .get("tekton.dev/categories", "")
                .split(",")
            )
            categories = [c.strip() for c in categories if c.strip()]
            task_versions.setdefault(name, {"versions": [], "categories": categories})[
                "versions"
            ].append((version_str, path))
        elif kind == "stepaction":
            # Store stepaction reference with version comparison
            current_version = self._stepaction_paths.get(name, {}).get("version", "")
            if not current_version or self._semantic_version_key(
                version_label
            ) > self._semantic_version_key(current_version):
                self._stepaction_paths[name] = {"version": version_label, "path": path}

            # Add to stepaction versions
            stepaction_versions.setdefault(name, []).append((version_str, path))
        elif kind == "pipeline":
            # Get group path without version directories
            group = self._get_group(file.src_path, self.nav_pipeline_grouping_offset)
            # Add debug logging
            self.logger.debug(f"Adding pipeline {name} to group {group}")
            pipeline_versions.setdefault(group, {}).setdefault(name, []).append(
                (version_str, path)
            )

    def _semantic_version_key(self, version_str):
        """Convert version string to comparable tuple"""
        return semantic_version_key(version_str)

    def _add_to_nav(self, nav_section, resources):
        if not isinstance(resources, dict):
            self.logger.error("Resources must be a dictionary, got %s", type(resources))
            return
        add_to_nav(nav_section, resources)

    def _update_navigation(self, nav, pipeline_versions, task_versions, stepaction_versions):
        """Update navigation structure"""
        self.logger.info("Updating navigation structure")

        pipelines_section = self._find_or_create_section(
            nav, self.nav_section_pipelines
        )
        tasks_section = self._find_or_create_section(nav, self.nav_section_tasks)
        stepactions_section = self._find_or_create_section(nav, self.nav_section_stepactions)

        if pipeline_versions:
            grouped_pipelines = {}

            # First pass - build nested structure
            for group, pipelines in pipeline_versions.items():
                parts = [p for p in group.split("/") if p]
                current = grouped_pipelines

                # Build full path
                for part in parts:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

                # Add pipelines to leaf node
                for name, versions in pipelines.items():
                    if isinstance(current, dict):
                        current[name] = versions

            # Second pass - build navigation
            def build_nav(section, structure):
                for key, value in sorted(structure.items()):
                    if isinstance(value, list):
                        # Direct pipeline versions
                        self._add_to_nav(section, {key: value})
                    else:
                        # Nested structure
                        subsection = self._find_or_create_section(section, key)
                        build_nav(subsection, value)

            self.logger.debug(f"Final structure: {grouped_pipelines}")
            build_nav(pipelines_section, grouped_pipelines)

        # Handle task versions
        if task_versions:
            if self.nav_group_tasks_by_category:
                categories = {}
                uncategorized = {}

                for task_name, task_info in task_versions.items():
                    versions = task_info["versions"]
                    task_categories = task_info.get("categories", [])

                    if not task_categories:
                        uncategorized[task_name] = versions
                    else:
                        for category in task_categories:
                            # Map category name if configured
                            mapped_category = self.config["nav_category_mapping"].get(
                                category, category
                            )
                            categories.setdefault(mapped_category, {})[
                                task_name
                            ] = versions

                if uncategorized:
                    self._add_to_nav(tasks_section, uncategorized)

                for category in sorted(categories.keys()):
                    category_section = self._find_or_create_section(
                        tasks_section, category
                    )
                    self._add_to_nav(category_section, categories[category])
            else:
                simplified_versions = {
                    name: info["versions"] for name, info in task_versions.items()
                }
                self._add_to_nav(tasks_section, simplified_versions)

        # Handle stepaction versions
        if stepaction_versions:
            self._add_to_nav(stepactions_section, stepaction_versions)

        if self.nav_hide_empty_sections:
            self._remove_empty_sections(nav)

    def _remove_empty_sections(self, nav_list):
        """Recursively remove empty sections from a navigation list."""
        remove_empty_sections(nav_list)

    def _find_or_create_section(self, nav, section_name):
        self.logger.debug("Finding or creating navigation section: %s", section_name)
        return find_or_create_section(nav, section_name)

    def _find_or_create_nested_dict(self, current_level, path_parts):
        self.logger.debug(
            "Finding or creating nested dict for path: %s", "/".join(path_parts)
        )
        for part in path_parts:
            found = False
            for item in current_level:
                if isinstance(item, dict) and part in item:
                    current_level = item[part]
                    found = True
                    break
            if not found:
                new_dict = {part: []}
                current_level.append(new_dict)
                current_level = new_dict[part]
        return current_level

    def _get_group(self, path, offset):
        """Extract group from path based on offset"""
        return get_group(path, offset)

    def _get_relative_path(self, from_path, to_path):
        """Generate relative path between two documents"""
        return get_relative_path(from_path, to_path)
