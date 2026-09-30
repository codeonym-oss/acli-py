"""Save an attachment to a local folder.

- `query.py`: `DownloadAttachment`, which attachment and where to; it changes nothing in Jira,
  so it is a query, but one that is never answered from the cache
- `handler.py`: reads the file's name, then saves its content through the `Attachments` port
- `view.py`: `SavedFile`, where it went and how big it is
"""
