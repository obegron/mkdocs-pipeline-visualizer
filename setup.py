from setuptools import setup, find_packages

setup(
    name="mkdocs-pipeline-visualizer",
    version="0.1.0",
    description="generate MD file from tekton pipelines and tasks, intended to be used together with mkdocs-techdocs-core",
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