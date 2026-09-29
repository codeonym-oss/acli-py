"""A friendly Jira Cloud command line, with a dry-run mode for every change."""

from importlib.metadata import version

__version__: str = version("acli-py")

__all__ = ["__version__"]
