from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from mediary.cqrs import stream_query_handler

from acli_py.application.ports import IssueSearch
from acli_py.application.queries.export_issues.query import ExportIssues
from acli_py.application.queries.issue_columns import columns, jira_fields
from acli_py.domain.issue import Issue

PAGE = 100


@stream_query_handler
async def export_issues(request: ExportIssues, search: IssueSearch) -> AsyncIterator[Issue]:
    """Yield the issues a page at a time; each page is read on a worker thread."""
    wanted = jira_fields(columns(request.fields)) or ("summary",)
    token: str | None = None
    sent = 0
    while request.limit is None or sent < request.limit:
        size = PAGE if request.limit is None else min(PAGE, request.limit - sent)
        issues, token = await asyncio.to_thread(
            search.search, request.jql, wanted, limit=size, token=token
        )
        for issue in issues:
            yield issue
        sent += len(issues)
        if not token or not issues:
            return
