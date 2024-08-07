import os
import yaml
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files

class PipelineVisualizer(BasePlugin):

    def pipeline_parameters(self, pipeline_params):
        markdown_content = "## Pipeline Parameters\n"
        if pipeline_params:
            markdown_content += "|Name|description|Default value|\n| --- | --- | --- |\n"
            for param in pipeline_params:
                name = param.get('name', 'Unnamed Parameter')
                description = param.get('description', 'No description available.')
                default = param.get('default', ' ')
                markdown_content += f"|{name}|`{description}`|{default}|\n"
        else:
            markdown_content += "No pipeline parameters specified.\n\n"
        return markdown_content

    def make_graph_from_tasks(self, tasks, final):
        markdown_content = "```@startuml\nleft to right direction\n!theme hacker\n"
        
        task_dependencies = {}
        all_tasks = set()
        tasks_with_dependencies = set()
        
        # Collect all task dependencies
        for task in tasks:
            task_name = task.get('name', 'Unnamed Task')
            run_after = task.get('runAfter', [])
            all_tasks.add(task_name)
            
            if not run_after:
                markdown_content += f"\"Start\" --> {task_name}\n"
            else:
                tasks_with_dependencies.add(task_name)
                for dependency in run_after:
                    if dependency not in task_dependencies:
                        task_dependencies[dependency] = []
                    task_dependencies[dependency].append(task_name)

        # Generate the task dependency diagram
        for task, dependencies in task_dependencies.items():
            for dependency in dependencies:
                markdown_content += f"\"{task}\" --> {dependency}\n"
        
        # Determine the end tasks (tasks with no dependencies after them)
        end_tasks = all_tasks - set(task_dependencies.keys())

        # Connect end tasks to the first "finally" task
        if final:
            finally_task = final[0].get('name', 'Finally Task')
            for end_task in end_tasks:
                markdown_content += f"\"{end_task}\" --> {finally_task}\n"

        markdown_content += "@enduml\n```\n"
        return markdown_content

    def visualize_parameters(self, params):
        markdown_content = "## Parameters\n\n"
        markdown_content += "| Name | Type | Description | Default |\n"
        markdown_content += "|------|------|-------------|--------|\n"
        for param in params:
            name = param.get('name', 'Unnamed Parameter')
            param_type = param.get('type', 'Not specified')
            description = param.get('description', 'No description provided.')
            default = param.get('default', 'Not specified')
            markdown_content += f"| `{name}` | `{param_type}` | {description} | `{default}` |\n"
        return markdown_content + "\n"

    def visualize_workspaces(self, workspaces):
        markdown_content = "## Workspaces\n\n"
        markdown_content += "| Name | Description | Optional |\n"
        markdown_content += "|------|-------------|----------|\n"
        for workspace in workspaces:
            name = workspace.get('name', 'Unnamed Workspace')
            description = workspace.get('description', ' ').replace('\n', '<br>')
            optional = workspace.get("optional",False)
            markdown_content += f"| `{name}` | {description} | { optional } |\n"
        return markdown_content + "\n"

    def visualize_tasks(self, tasks):
        markdown_content = "## Tasks\n\n"
        for task in tasks:
            task_name = task.get('name', 'Unnamed Task')
            markdown_content += f"### {task_name}\n\n"
            
            # Task Reference
            task_ref = task.get('taskRef', {})
            markdown_content += f"**Task Reference:** `{task_ref.get('name', 'Not specified')}`\n\n"
            
            # Run After
            run_after = task.get('runAfter', [])
            if run_after:
                markdown_content += "**Runs After:**\n\n"
                for dep in run_after:
                    markdown_content += f"- `{dep}`\n"
                markdown_content += "\n"
            
            # Parameters
            params = task.get('params', [])
            if params:
                markdown_content += "**Parameters:**\n\n"
                markdown_content += "| Name | Value |\n"
                markdown_content += "|------|-------|\n"
                for param in params:
                    name = param.get('name', 'Unnamed Parameter')
                    value = param.get('value', 'Not specified')
                    if isinstance(value, list):
                        value = "<ul>" + "".join(f"<li>{v}</li>" for v in value) + "</ul>"
                    elif isinstance(value, str) and '\n' in value:
                        value = value.replace('\n', '<br>')
                    if '<br>' in str(value) or '<ul>' in str(value):
                        markdown_content += f"| `{name}` | {value} |\n"
                    else:
                        markdown_content += f"| `{name}` | `{value}` |\n"
                markdown_content += "\n"
            
            # Workspaces
            workspaces = task.get('workspaces', [])
            if workspaces:
                markdown_content += "**Workspaces:**\n\n"
                markdown_content += "| Name | Workspace |\n"
                markdown_content += "|------|----------|\n"
                for workspace in workspaces:
                    name = workspace.get('name', 'Unnamed Workspace')
                    workspace_name = workspace.get('workspace', 'Not specified')
                    markdown_content += f"| `{name}` | `{workspace_name}` |\n"
                markdown_content += "\n"
            
            markdown_content += "---\n\n"
        
        return markdown_content

    def visualize_steps(self, steps):
        markdown_content = "## Steps\n\n"
        for i, step in enumerate(steps, 1):
            step_name = step.get('name', f'Step {i}')
            markdown_content += f"### {step_name}\n\n"
            
            # Image
            image = step.get('image', 'Not specified')
            markdown_content += f"**Image:** `{image}`\n\n"
            
            # Command
            command = step.get('command', [])
            if command:
                markdown_content += "**Command:**\n\n```\n"
                markdown_content += ' '.join(command)
                markdown_content += "\n```\n\n"
            
            # Args
            args = step.get('args', [])
            if args:
                markdown_content += "**Arguments:**\n\n```\n"
                markdown_content += ' '.join(args)
                markdown_content += "\n```\n\n"
            
            # Environment Variables
            env = step.get('env', [])
            if env:
                markdown_content += "**Environment Variables:**\n\n"
                markdown_content += "| Name | Value |\n"
                markdown_content += "|------|-------|\n"
                for var in env:
                    name = var.get('name', 'Unnamed Variable')
                    value = var.get('value', 'Not specified')
                    markdown_content += f"| `{name}` | `{value}` |\n"
                markdown_content += "\n"
            
            markdown_content += "---\n\n"
        
        return markdown_content

    def visualize_results(self, results):
        markdown_content = "## Results\n\n"
        markdown_content += "| Name | Description |\n"
        markdown_content += "|------|-------------|\n"
        for result in results:
            name = result.get('name', 'Unnamed Result')
            description = result.get('description', 'No description provided.')
            markdown_content += f"| `{name}` | {description} |\n"
        return markdown_content + "\n"

    def on_files(self, files, config):
        new_files = []
        for file in files:            
            if file.src_path.endswith(".yaml"):
                # Generate the Markdown content from the YAML file
                with open(file.abs_src_path, 'r') as f:
                    try:
                        # Load all documents in the YAML file
                        resources = list(yaml.safe_load_all(f))
                    except yaml.YAMLError as e:
                        print(f"Error parsing YAML file {file.src_path}: {e}")
                        continue

                markdown_content = ""
                for resource in resources:
                    kind = resource.get('kind', '')
                    metadata = resource.get('metadata', {})
                    spec = resource.get('spec', {})
                    resource_name = metadata.get('name', 'Unnamed Resource')

                    markdown_content += f"# {kind}: {resource_name}\n\n"

                    if kind.lower() == 'pipeline':
                        tasks = spec.get('tasks', [])
                        final = spec.get('finally', [])
                        markdown_content += self.make_graph_from_tasks(tasks, final)
                        markdown_content += self.visualize_parameters(spec.get('params', []))
                        markdown_content += self.visualize_workspaces(spec.get('workspaces', []))
                        markdown_content += self.visualize_tasks(tasks)
                        if final:
                            markdown_content += "## Finally\n\n"
                            markdown_content += self.visualize_tasks(final)
                    elif kind.lower() == 'task':
                        markdown_content += f"## Description\n{spec.get('description','No description')}\n"
                        markdown_content += self.visualize_parameters(spec.get('params', []))
                        markdown_content += self.visualize_workspaces(spec.get('workspaces', []))
                        markdown_content += self.visualize_steps(spec.get('steps', []))
                        markdown_content += self.visualize_results(spec.get('results', []))
                    else:
                        continue

                    markdown_content += "\n---\n\n"  # Add separator between resources

                # Ensure the directory structure exists
                os.makedirs(os.path.dirname(file.abs_src_path.replace('.yaml', '.md')), exist_ok=True)

                with open(file.abs_src_path.replace('.yaml', '.md'), 'w') as f:
                    f.write(markdown_content)
                
                # Add entry for the new file
                new_file = File(
                    file.src_path.replace('.yaml', '.md'),
                    file.src_dir,
                    file.dest_dir,
                    config['site_dir']
                )
                new_files.append(new_file)
            else:
                new_files.append(file)
        
        self.update_nav(config['nav'])
        return Files(new_files)

    def update_nav(self, nav):
        # Recursively update the nav entries
        for idx, item in enumerate(nav):
            if isinstance(item, dict):
                for key, value in item.items():
                    if isinstance(value, str) and value.endswith('.yaml'):
                        nav[idx][key] = value.replace('.yaml', '.md')
                    elif isinstance(value, list):
                        self.update_nav(value)
            elif isinstance(item, str) and item.endswith('.yaml'):
                nav[idx] = item.replace('.yaml', '.md')