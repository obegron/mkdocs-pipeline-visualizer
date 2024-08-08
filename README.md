# mkdocs-mkdocs-pipeline-visualizer



## Usage

```bash
$ pip install mkdocs-pipeline-visualizer
```

Example of mkdocs.yaml

```yaml
site_name: Tekton

nav:
  - Home: index.md
  - Deployment Pipeline: ./path/to/pipeline/deploy-pipeline.md

plugins:
  - pipeline-visualizer
```

./path/to/pipeline/deploy-pipeline.md is the path to the actual pipeline definition but replace the extension from `.yaml` to `.md`

(Optional) configuration these are the default values

```yaml
plugins:
  - pipeline-visualizer:
      plantuml_graphs: True
      plantuml_graph_direction: TB
      plantuml_theme: _none_
```

* `plantuml_graphs` **[bool]** controls if pipeline graph should be visible
* `plantuml_graph_direction` **[string]**  TB(top to bottom) or LR(left to right)
* `plantuml_theme` **[string]** any theme from https://plantuml.com/theme to style plantuml_theme e.g hacker, spacelab

## Changelog

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
* fix issue with multicods
