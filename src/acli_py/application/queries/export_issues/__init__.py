"""Every issue a search finds, streamed a page at a time, for exports of any size.

- `query.py`: `ExportIssues`, a stream query: the JQL, and the columns to fetch
- `handler.py`: an async generator over the `IssueSearch` port, yielding each `Issue` as
  its page arrives, so the front end writes rows without holding them all
"""
