import os
import yaml
import logging
import hashlib
from typing import Any
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

KIND_PIPELINE = "pipeline"
KIND_TASK = "task"
KIND_STEPACTION = "stepaction"


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

    def __init__(self) -> None:
        self.logger = logging.getLogger("mkdocs.plugins.pipeline_visualizer")
        self._task_paths: dict[str, dict[str, str]] = {}
        self._stepaction_paths: dict[str, dict[str, str]] = {}

    def on_config(self, config: dict[str, Any]) -> None:
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

    def _parse_grouping_offset(self, offset_str: str | None) -> tuple[int, int] | None:
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
                "Invalid grouping offset format: %s. Using default (None).",
                offset_str,
            )
            return None

    def on_files(self, files: Files, config: dict[str, Any]) -> Files:
        pipeline_versions: dict[str, dict[str, list[tuple[str, str]]]] = {}
        task_versions: dict[str, dict[str, Any]] = {}
        stepaction_versions: dict[str, list[tuple[str, str]]] = {}
        new_files: list[File] = []
        yaml_files = [file for file in files if file.src_path.endswith(".yaml")]
        resources_by_path = self._collect_yaml_resources(yaml_files)

        # Process tasks and stepactions first to build task reference map
        for file in yaml_files:
            resources = resources_by_path.get(file.src_path)
            if not resources:
                continue
            kinds = self._resource_kinds(resources)
            if KIND_TASK in kinds or KIND_STEPACTION in kinds:
                new_file = self._process_yaml_file(
                    file,
                    config,
                    pipeline_versions,
                    task_versions,
                    stepaction_versions,
                    resources,
                )
                if new_file:
                    new_files.append(new_file)

        # Then process pipelines with complete task reference map
        for file in yaml_files:
            resources = resources_by_path.get(file.src_path)
            if not resources:
                continue
            kinds = self._resource_kinds(resources)
            if KIND_PIPELINE in kinds:
                new_file = self._process_yaml_file(
                    file,
                    config,
                    pipeline_versions,
                    task_versions,
                    stepaction_versions,
                    resources,
                )
                if new_file:
                    new_files.append(new_file)

        if self.nav_generation:
            self._update_navigation(config["nav"], pipeline_versions, task_versions, stepaction_versions)

        return Files(list(files) + [f for f in new_files if f is not None])

    def _collect_yaml_resources(
        self, yaml_files: list[File]
    ) -> dict[str, list[dict[str, Any]]]:
        resources_by_path: dict[str, list[dict[str, Any]]] = {}
        for file in yaml_files:
            resources = self._load_yaml(file.abs_src_path)
            if resources:
                resources_by_path[file.src_path] = resources
        return resources_by_path

    def _resource_kinds(self, resources: list[dict[str, Any]]) -> set[str]:
        return {
            resource.get("kind", "").lower()
            for resource in resources
            if isinstance(resource, dict)
        }

    def _process_yaml_file(
        self,
        file: File,
        config: dict[str, Any],
        pipeline_versions: dict[str, dict[str, list[tuple[str, str]]]],
        task_versions: dict[str, dict[str, Any]],
        stepaction_versions: dict[str, list[tuple[str, str]]],
        resources: list[dict[str, Any]] | None = None,
    ) -> File | None:
        """Process YAML file containing one or more resources"""
        resources = resources if resources is not None else self._load_yaml(file.abs_src_path)
        if not resources:
            self.logger.warning("Failed to load YAML file: %s", file.abs_src_path)
            return None

        # Sort resources to ensure tasks are processed first
        resources.sort(key=lambda x: x.get("kind", "").lower() != "task")

        content = self._generate_markdown_content(resources, file.src_path)
        new_file = self._create_markdown_file(file, config, content)

        if new_file:
            for resource in resources:
                kind = resource.get("kind", "").lower()
                if kind in [KIND_PIPELINE, KIND_TASK, KIND_STEPACTION]:
                    self._add_to_versions(
                        resource, new_file, kind, pipeline_versions, task_versions, stepaction_versions
                    )

        return new_file

    def _load_yaml(self, file_path: str) -> list[dict[str, Any]] | None:
        """Load YAML file, supporting multiple documents"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return None
                documents = list(yaml.safe_load_all(content))
                valid_docs = [doc for doc in documents if doc and isinstance(doc, dict)]
                return valid_docs if valid_docs else None
        except yaml.YAMLError as e:
            self.logger.error("Error parsing YAML file %s: %s", file_path, e)
            return None
        except OSError as e:
            self.logger.error("Error reading YAML file %s: %s", file_path, e)
            return None

    def _create_markdown_file(
        self,
        original_file: File,
        config: dict[str, Any],
        content: str,
        suffix: str = "",
    ) -> File:
        """Create markdown file with optional suffix for multi-doc files"""
        base_path = original_file.abs_src_path.replace(".yaml", f"{suffix}.md")
        os.makedirs(os.path.dirname(base_path), exist_ok=True)

        new_content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        # Check if file exists and content is the same
        if os.path.exists(base_path):
            with open(base_path, "r", encoding="utf-8") as f:
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

        with open(base_path, "w", encoding="utf-8") as f:
            f.write(content)

        self.logger.debug("Created Markdown file: %s", base_path)
        return File(
            original_file.src_path.replace(".yaml", f"{suffix}.md"),
            original_file.src_dir,
            original_file.dest_dir,
            config["site_dir"],
        )

    def _renderer(self, source_path: str) -> MarkdownRenderer:
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

    def _navigation_builder(self) -> NavigationBuilder:
        plugin_config = getattr(self, "config", {})
        return NavigationBuilder(
            logger=self.logger,
            nav_section_pipelines=getattr(self, "nav_section_pipelines", "Pipelines"),
            nav_section_tasks=getattr(self, "nav_section_tasks", "Tasks"),
            nav_section_stepactions=getattr(
                self, "nav_section_stepactions", "StepActions"
            ),
            nav_group_tasks_by_category=getattr(
                self, "nav_group_tasks_by_category", False
            ),
            nav_category_mapping=plugin_config.get("nav_category_mapping", {}),
            nav_hide_empty_sections=getattr(self, "nav_hide_empty_sections", False),
        )

    def _generate_markdown_content(
        self, resources: list[dict[str, Any]], source_path: str
    ) -> str:
        return self._renderer(source_path).generate_markdown_content(resources)

    def _generate_cli_command(
        self, metadata: dict[str, Any], spec: dict[str, Any], kind: str = "task"
    ) -> str:
        return self._renderer("").generate_cli_command(metadata, spec, kind)

    def _get_task_categories(self, metadata: dict[str, Any]) -> list[str]:
        """Extract categories from task metadata"""
        if metadata and "annotations" in metadata:
            categories = metadata["annotations"].get("tekton.dev/categories", "")
            return [c.strip() for c in categories.split(",") if c.strip()]
        return []

    def _add_to_versions(
        self,
        resource: dict[str, Any],
        file: File,
        kind: str,
        pipeline_versions: dict[str, dict[str, list[tuple[str, str]]]],
        task_versions: dict[str, dict[str, Any]],
        stepaction_versions: dict[str, list[tuple[str, str]]],
    ) -> None:
        metadata = resource.get("metadata", {})
        name = metadata.get("name", "Unnamed Resource")
        version_label = metadata.get("labels", {}).get("app.kubernetes.io/version", "")
        version_str = version_label
        path = file.src_path.replace("\\", "/")

        if kind == KIND_TASK:
            # Store task reference with version comparison
            current_version = self._task_paths.get(name, {}).get("version", "")
            if not current_version or self._semantic_version_key(
                version_label
            ) > self._semantic_version_key(current_version):
                self._task_paths[name] = {"version": version_label, "path": path}

            # Add to task versions
            categories = self._get_task_categories(metadata)
            task_versions.setdefault(name, {"versions": [], "categories": categories})[
                "versions"
            ].append((version_str, path))
        elif kind == KIND_STEPACTION:
            # Store stepaction reference with version comparison
            current_version = self._stepaction_paths.get(name, {}).get("version", "")
            if not current_version or self._semantic_version_key(
                version_label
            ) > self._semantic_version_key(current_version):
                self._stepaction_paths[name] = {"version": version_label, "path": path}

            # Add to stepaction versions
            stepaction_versions.setdefault(name, []).append((version_str, path))
        elif kind == KIND_PIPELINE:
            # Get group path without version directories
            group = self._get_group(file.src_path, self.nav_pipeline_grouping_offset)
            # Add debug logging
            self.logger.debug("Adding pipeline %s to group %s", name, group)
            pipeline_versions.setdefault(group, {}).setdefault(name, []).append(
                (version_str, path)
            )

    def _semantic_version_key(self, version_str: str) -> Any:
        """Convert version string to comparable tuple"""
        return semantic_version_key(version_str)

    def _add_to_nav(
        self, nav_section: list[dict[str, Any]], resources: dict[str, Any]
    ) -> None:
        if not isinstance(resources, dict):
            self.logger.error("Resources must be a dictionary, got %s", type(resources))
            return
        add_to_nav(nav_section, resources)

    def _update_navigation(
        self,
        nav: list[dict[str, Any]],
        pipeline_versions: dict[str, dict[str, list[tuple[str, str]]]],
        task_versions: dict[str, dict[str, Any]],
        stepaction_versions: dict[str, list[tuple[str, str]]],
    ) -> None:
        self._navigation_builder().update_navigation(
            nav, pipeline_versions, task_versions, stepaction_versions
        )

    def _remove_empty_sections(self, nav_list: list[dict[str, Any]]) -> None:
        """Recursively remove empty sections from a navigation list."""
        remove_empty_sections(nav_list)

    def _find_or_create_section(
        self, nav: list[dict[str, Any]], section_name: str
    ) -> list[dict[str, Any]]:
        self.logger.debug("Finding or creating navigation section: %s", section_name)
        return find_or_create_section(nav, section_name)

    def _get_group(self, path: str, offset: tuple[int, int] | None) -> str:
        """Extract group from path based on offset"""
        return get_group(path, offset)

    def _get_relative_path(self, from_path: str, to_path: str) -> str:
        """Generate relative path between two documents"""
        return get_relative_path(from_path, to_path)
