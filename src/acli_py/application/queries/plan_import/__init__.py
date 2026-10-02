"""Work out what importing rows of issues changes, before anything is changed.

- `query.py`: `PlanImport`, the rows (CSV or JSON objects), and where new issues go
- `handler.py`: maps each column to a field, then each row with a key to an edit of what
  differs from the issue now, and each row without one to a new issue
- `view.py`: `ImportPlan`: the column mapping, the commands and their preview

Front ends run the plan through the bulk engine (`bus.bulk.run(plan.commands,
change=plan.change(), name="ImportIssues")`): it asks once, runs a few rows at a time,
reports each, and keeps one audit record (which `undo` can reverse, edits only).
"""
