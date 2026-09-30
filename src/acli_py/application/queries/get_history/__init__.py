"""An issue's history: who changed what, and when.

- `query.py`: `GetHistory`, which issue, which field, which way round
- `handler.py`: reads the changelog through the `IssueReader` port
- `view.py`: `HistoryView`, one row per field changed, as JSON
"""
