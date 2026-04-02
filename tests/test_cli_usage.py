import logging

import pytest

from mkdocs_pipeline_visualizer.visualizer import PipelineVisualizer

@pytest.fixture
def plugin():
    p = PipelineVisualizer()
    p.include_cli_usage = True
    return p

def test_generate_cli_command_task(plugin):
    metadata = {"name": "test-task"}
    spec = {}
    
    cmd = plugin._generate_cli_command(metadata, spec, kind="task")
    assert "tkn task start test-task" in cmd

def test_generate_cli_command_pipeline(plugin):
    metadata = {"name": "test-pipeline"}
    spec = {}
    
    cmd = plugin._generate_cli_command(metadata, spec, kind="pipeline")
    assert "tkn pipeline start test-pipeline" in cmd

def test_generate_cli_command_with_params(plugin):
    metadata = {"name": "test-resource"}
    spec = {
        "params": [
            {"name": "param1"},
            {"name": "param2", "default": "value2"}
        ]
    }
    
    cmd = plugin._generate_cli_command(metadata, spec, kind="pipeline")
    assert "-p param1=<PARAM1>" in cmd
    assert "-p param2" not in cmd # Default values are skipped

def test_generate_cli_command_with_workspaces(plugin):
    metadata = {"name": "test-resource"}
    spec = {
        "workspaces": [
            {"name": "source"},
            {"name": "optional-ws", "optional": True}
        ]
    }
    
    cmd = plugin._generate_cli_command(metadata, spec, kind="task")
    assert "-w source=<SOURCE>" in cmd
    assert "-w optional-ws" not in cmd
