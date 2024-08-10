# mkdocs-mkdocs-pipeline-visualizer



## Usage

```bash
$ pip install mkdocs-pipeline-visualizer
```

Example of mkdocs.yaml

```yaml
site_name: Tekton
docs_dir: ./tekton

nav:
  - Home: index.md

plugins:
  - pipeline-visualizer

markdown_extensions:
  plantuml_markdown:
    server: http://www.plantuml.com/plantuml

theme:
  name: material
  features:
    - navigation.sections
```

Default it creates two sections in root Pipelines and Tasks, doc_dir should point to directory pipelines and tasks

| Config parameter | Type | Description | Default | Implemented in |
| ---------------- | ---- | ----------- | ------- | -------------- |
| `plantuml_graphs`| **[bool]** | Controls if pipeline graph should be visible | `True` | 0.1.5 |
| `plantuml_graph_direction` | **[string]** | TB(top to bottom) or LR(left to right) | `TB` | 0.1.3 |
| `plantuml_theme` | **[string]** | any theme from https://plantuml.com/theme to style e.g hacker, spacelab | `_none_` | 0.1.3 |
| `nav_generation` | **[bool]** | automatically generate navigation tree | `True` | 0.2.0 |
| `nav_section_pipelines` | **[string]** | section name used for pipelines | `Pipelines` | 0.2.0 |
| `nav_section_tasks` | **[string]** | section name used for tasks | `Tasks` | 0.2.0 |

## HowTo

You can change location of documentation. Place a empty Section in any location of nav with the value of `nav_section_pipeline` or `nav_section_tasks`

```yaml
site_name: Tekton
docs_dir: ./tekton

nav:
  - Home: index.md
  - Tekton:
    - "Tasks": []
    - "Pipelines": []

plugins:
  - pipeline-visualizer
```

To change the menu section name and custom graph theme

```yaml
site_name: Tekton
docs_dir: ./tekton

nav:
  - Home: index.md  
  - Tekton:
    - "🛠️ Tasks": []
    - "🚀 Pipelines": []

plugins:
  - pipeline-visualizer:
      plantuml_theme: hacker
      nav_section_tasks: "🛠️ Tasks"
      nav_section_pipelines: "🚀 Pipelines"
```

## Changelog

# 0.2.0
* generate nav tree by default
* enable change change of section names and locations

# 0.1.8
* remove version of tasks until there is a nicer way to present it

# 0.1.7
* fix issue with \ in usage
* correct example in readme

# 0.1.6
* hide workspaces for tasks when none are used
* show version of pipeline/task when available 

# 0.1.5
* remove extra --- after tasks
* sample of how to use task in pipeline
* make plantuml graphs optional using boolean `plantuml_graphs` default true
* only process pipeline or tasks

# 0.1.4
* show all tasks in finally block

# 0.1.3
* enable configuration of graph direction `plantuml_graph_direction` either TB or LR
* configuration for plantuml theme `plantuml_theme` string (https://plantuml.com/theme)
* display references to configMaps

# 0.1.2
* remove unused code
* change how default and empty values are presented

# 0.1.1
* fix issue with multidocs
