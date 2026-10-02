"""The changes the audit log keeps, newest first.

- `query.py`: `ListChanges`, how many
- `handler.py`: reads them through the `AuditLog` port
- `view.py`: `ChangesView`, which says which were undone, as JSON
"""
