"""Presentation: the front ends. They turn what people type into messages and show the answers.

`cli/` is the Typer command line, `shell.py` the prompt, `tui/` the Textual browser, and
`output.py` what all of them print. They reach Jira only through the bus from
`acli_py.bootstrap`.
"""
