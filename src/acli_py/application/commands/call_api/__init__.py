"""A write to any REST endpoint (reads are the `ApiGet` query).

- `command.py`: `CallApi`; it doesn't ask first, as the raw API never did, but dry runs
  plan it and the audit log keeps it
- `handler.py`: sends it through the `RawApi` port
"""
