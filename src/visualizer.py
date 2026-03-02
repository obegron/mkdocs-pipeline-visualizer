import os
import yaml
import logging
import hashlib
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files
from mkdocs.config import config_options
from .markdown_renderer import MarkdownRenderer
from .navigation_builder import NavigationBuilder
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

    def _renderer(self, source_path):
        return MarkdownRenderer(
            logger=self.logger,
            plantuml_graphs=getattr(self, "plantuml_graphs", True),
            plantuml_graph_direction=getattr(
                self, "plantuml_graph_direction", "top to bottom direction"
            ),
            plantuml_theme=getattr(self, "plantuml_theme", "_none_"),
            include_cli_usage=getattr(self, "include_cli_usage", True),
            task_paths=self._task_paths,
            stepaction_paths=self._stepaction_paths,
            relative_path_fn=self._get_relative_path,
            source_path=source_path,
        )

    def _navigation_builder(self):
        return NavigationBuilder(
            logger=self.logger,
            nav_section_pipelines=self.nav_section_pipelines,
            nav_section_tasks=self.nav_section_tasks,
            nav_section_stepactions=self.nav_section_stepactions,
            nav_group_tasks_by_category=self.nav_group_tasks_by_category,
            nav_category_mapping=self.config.get("nav_category_mapping", {}),
            nav_hide_empty_sections=self.nav_hide_empty_sections,
        )

    def _generate_markdown_content(self, resources, source_path):
        return self._renderer(source_path).generate_markdown_content(resources)

    def _visualize_pipeline(self, spec, source_path):
        return self._renderer(source_path).visualize_pipeline(spec)

    def _visualize_task(self, metadata, spec, source_path):
        return self._renderer(source_path).visualize_task(metadata, spec)

    def _visualize_stepaction(self, metadata, spec):
        return self._renderer("").visualize_stepaction(metadata, spec)

    def _make_graph_from_tasks(self, tasks, final):
        return self._renderer("").make_graph_from_tasks(tasks, final)

    def _visualize_step_template(self, template):
        return self._renderer("").visualize_step_template(template)

    def _visualize_parameters(self, params):
        return self._renderer("").visualize_parameters(params)

    def _visualize_workspaces(self, workspaces):
        return self._renderer("").visualize_workspaces(workspaces)

    def _visualize_tasks(self, tasks, source_path):
        return self._renderer(source_path).visualize_tasks(tasks)

    def _visualize_steps(self, steps, source_path):
        return self._renderer(source_path).visualize_steps(steps)

    def _visualize_common_elements(self, spec):
        return self._renderer("").visualize_common_elements(spec)

    def _visualize_results(self, results):
        return self._renderer("").visualize_results(results)

    def _visualize_environment(self, env):
        return self._renderer("").visualize_environment(env)

    def _visualize_usage(self, metadata, spec, kind="task"):
        return self._renderer("").visualize_usage(metadata, spec, kind)

    def _generate_cli_command(self, metadata, spec, kind="task"):
        return self._renderer("").generate_cli_command(metadata, spec, kind)

    def _format_value(self, value):
        return self._renderer("").format_value(value)

    def _table_with_header(self, header, table_headers):
        return self._renderer("").table_with_header(header, table_headers)

    def _render_script(self, script):
        return self._renderer("").render_script(script)

    def _render_command(self, command):
        return self._renderer("").render_command(command)

    def _render_args(self, args):
        return self._renderer("").render_args(args)

    def _render_resource_reference(self, label, ref_name, resource_paths, source_path):
        return self._renderer(source_path).render_resource_reference(
            label=label, ref_name=ref_name, resource_paths=resource_paths
        )

    def _get_script_type(self, script):
        return self._renderer("").detect_script_type(script)

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
        self._navigation_builder().update_navigation(
            nav, pipeline_versions, task_versions, stepaction_versions
        )

    def _remove_empty_sections(self, nav_list):
        """Recursively remove empty sections from a navigation list."""
        remove_empty_sections(nav_list)

    def _find_or_create_section(self, nav, section_name):
        self.logger.debug("Finding or creating navigation section: %s", section_name)
        return find_or_create_section(nav, section_name)

    def _get_group(self, path, offset):
        """Extract group from path based on offset"""
        return get_group(path, offset)

    def _get_relative_path(self, from_path, to_path):
        """Generate relative path between two documents"""
        return get_relative_path(from_path, to_path)
