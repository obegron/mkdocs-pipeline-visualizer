from setuptools import setup, find_packages
from os import path

this_dir = path.abspath(path.dirname(__file__))
with open(path.join(this_dir, "README.md"), encoding="utf-8") as file:
    long_description = file.read()

setup(
    name="mkdocs-pipeline-visualizer",
    version="0.1.7",
    description="generate MD documentation from tekton pipelines and tasks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/obegron/mkdocs-pipeline-visualizer",
    packages=find_packages(),
    author='Christer Grönblad',
    install_requires=['mkdocs'],
    entry_points={
        'mkdocs.plugins': [
            'pipeline-visualizer = src.visualizer:PipelineVisualizer'
        ]
    }
)