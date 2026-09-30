# acli-py

`acli-py` is a friendly command line for **Jira Cloud**: a Python port of the Jira side of
Atlassian's `acli`, redesigned around short, predictable commands and a **dry-run mode for
every change**.

```sh
acli-py auth login
acli-py issue create -p DEMO -t Bug -s "Login fails on Safari" -a @me -L web
acli-py issue transition DEMO-12 --to "In Progress" -m "On it"
acli-py issue edit --jql 'project = DEMO AND labels = legacy' --remove-label legacy --dry-run
acli-py issue search '@me is:open #web sort:-priority'
acli-py tui
```

Start with [Getting started](guide/getting-started.md), then try the
[TUI and the shell](guide/interactive.md). [Dry runs and bulk changes](guide/dry-run.md)
explains how changes are previewed and applied to many issues, and [Pipes](guide/pipes.md)
how to chain commands. Every command is listed under
[Commands](commands/index.md), generated from the CLI's own help.

```{toctree}
:hidden:
:caption: Guide

guide/getting-started
guide/interactive
guide/dry-run
guide/pipes
guide/fields
guide/from-acli
```

```{toctree}
:hidden:
:caption: Reference

commands/index
```

```{toctree}
:hidden:
:caption: Design

adr/0001-layers
```
