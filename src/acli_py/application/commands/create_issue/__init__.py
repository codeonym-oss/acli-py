"""Create an issue, from fields as Jira takes them (or from a few plain values).

- `command.py`: `CreateIssue`, the fields; it shows itself in a preview without asking Jira
- `handler.py`: creates it through the `IssueStore` port and returns what `Changed`
"""
