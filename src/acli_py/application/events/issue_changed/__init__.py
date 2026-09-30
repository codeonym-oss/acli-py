"""An issue changed: every command that touches an issue ends by publishing this.

- `event.py`: `IssueChanged`, with the fields before and after
- `subscribers.py`: drop cached answers, record the change in the audit log, tell the screens
"""
