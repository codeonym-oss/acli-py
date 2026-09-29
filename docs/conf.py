"""Sphinx configuration: MyST pages, Shibuya theme."""

from importlib.metadata import version as _version

project = "acli-py"
author = "codeonym-oss"
copyright = "codeonym-oss — MIT License"
release = _version("acli-py")
version = ".".join(release.split(".")[:2])

extensions = ["myst_parser"]
exclude_patterns = ["_build"]

# Pages: Markdown, with ```{directive} blocks and `#heading` anchors for links.
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

html_theme = "shibuya"
html_title = "acli-py"
html_baseurl = "https://docs.codeonym.work/projects/acli-py/"
html_context = {
    "source_type": "github",
    "source_user": "codeonym-oss",
    "source_repo": "acli-py",
    "source_version": "main",
    "source_docs_path": "/docs/",
}
html_theme_options = {
    "accent_color": "indigo",
    "github_url": "https://github.com/codeonym-oss/acli-py",
    "nav_links": [
        {"title": "Guide", "url": "guide/getting-started"},
        {"title": "Commands", "url": "commands/index"},
    ],
}
