from .navigation_utils import add_to_nav, find_or_create_section, remove_empty_sections


class NavigationBuilder:
    def __init__(
        self,
        logger,
        nav_section_pipelines,
        nav_section_tasks,
        nav_section_stepactions,
        nav_group_tasks_by_category,
        nav_category_mapping,
        nav_hide_empty_sections,
    ):
        self.logger = logger
        self.nav_section_pipelines = nav_section_pipelines
        self.nav_section_tasks = nav_section_tasks
        self.nav_section_stepactions = nav_section_stepactions
        self.nav_group_tasks_by_category = nav_group_tasks_by_category
        self.nav_category_mapping = nav_category_mapping
        self.nav_hide_empty_sections = nav_hide_empty_sections

    def update_navigation(self, nav, pipeline_versions, task_versions, stepaction_versions):
        self.logger.info("Updating navigation structure")

        pipelines_section = self.find_or_create_section(nav, self.nav_section_pipelines)
        tasks_section = self.find_or_create_section(nav, self.nav_section_tasks)
        stepactions_section = self.find_or_create_section(nav, self.nav_section_stepactions)

        if pipeline_versions:
            grouped_pipelines = {}

            for group, pipelines in pipeline_versions.items():
                parts = [p for p in group.split("/") if p]
                current = grouped_pipelines

                for part in parts:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

                for name, versions in pipelines.items():
                    if isinstance(current, dict):
                        current[name] = versions

            def build_nav(section, structure):
                for key, value in sorted(structure.items()):
                    if isinstance(value, list):
                        self.add_to_nav(section, {key: value})
                    else:
                        subsection = self.find_or_create_section(section, key)
                        build_nav(subsection, value)

            self.logger.debug(f"Final structure: {grouped_pipelines}")
            build_nav(pipelines_section, grouped_pipelines)

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
                            mapped_category = self.nav_category_mapping.get(
                                category, category
                            )
                            categories.setdefault(mapped_category, {})[task_name] = versions

                if uncategorized:
                    self.add_to_nav(tasks_section, uncategorized)

                for category in sorted(categories.keys()):
                    category_section = self.find_or_create_section(tasks_section, category)
                    self.add_to_nav(category_section, categories[category])
            else:
                simplified_versions = {
                    name: info["versions"] for name, info in task_versions.items()
                }
                self.add_to_nav(tasks_section, simplified_versions)

        if stepaction_versions:
            self.add_to_nav(stepactions_section, stepaction_versions)

        if self.nav_hide_empty_sections:
            self.remove_empty_sections(nav)

    def add_to_nav(self, nav_section, resources):
        if not isinstance(resources, dict):
            self.logger.error("Resources must be a dictionary, got %s", type(resources))
            return
        add_to_nav(nav_section, resources)

    def remove_empty_sections(self, nav_list):
        remove_empty_sections(nav_list)

    def find_or_create_section(self, nav, section_name):
        self.logger.debug("Finding or creating navigation section: %s", section_name)
        return find_or_create_section(nav, section_name)
