"""An issue's links to other issues.

- `query.py`: `ListLinks`, which issue
- `handler.py`: reads them through the `IssueLinks` port
- `view.py`: `LinksView`, one row per link, keyed by the other issue (so `--output keys` pipes them)
"""
