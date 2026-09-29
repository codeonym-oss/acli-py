"""The handlers behind each query and command: plain functions over the Jira client.

They are sync, so mediary runs each on a worker thread and the UI never blocks on the network.
Their `Site` parameter is supplied by the mediator's resolver.
"""

from __future__ import annotations

from typing import Any

from mediary.cqrs import command_handler, query_handler

from acli_py.application.messages import (
    AssignIssue,
    CommentOnIssue,
    CountIssues,
    CreateIssue,
    FindAssignees,
    GetTransitions,
    ListFilters,
    ListIssueTypes,
    ListPriorities,
    ListProjects,
    Page,
    SearchIssues,
    TransitionIssue,
    UpdateIssue,
    ValidateJql,
    WatchIssue,
)
from acli_py.application.site import Site
from acli_py.domain import adf
from acli_py.infrastructure.jira.client import API

# ── queries ──────────────────────────────────────────────────────────────────


@query_handler
def search_issues(request: SearchIssues, site: Site) -> Page:
    """Return one page of results."""
    issues, token = site.client.search_page(
        request.jql, list(request.fields), size=request.size, token=request.token
    )
    return Page(issues, token, request.jql)


@query_handler
def count_issues(request: CountIssues, site: Site) -> int:
    """Return the approximate count."""
    return site.client.count(request.jql)


@query_handler
def get_transitions(request: GetTransitions, site: Site) -> list:
    """Return the transitions available now."""
    return site.client.transitions(request.key)


@query_handler
def find_assignees(request: FindAssignees, site: Site) -> list:
    """Return assignable people matching the text."""
    found = site.client.get(
        f"{API}/user/assignable/search",
        issueKey=request.key,
        query=request.text or None,
        maxResults=20,
    )
    return [u for u in found or [] if u.get("accountType", "atlassian") == "atlassian"]


@query_handler
def validate_jql(request: ValidateJql, site: Site) -> list:
    """Return Jira's complaints about the query."""
    return site.client.validate_jql(request.jql)


@query_handler
def list_filters(request: ListFilters, site: Site) -> list:
    """Return favourite filters."""
    return list(site.client.get(f"{API}/filter/favourite") or [])


@query_handler
def list_priorities(request: ListPriorities, site: Site) -> list:
    """Return the priorities."""
    return list(site.client.paged(f"{API}/priority/search", limit=100))


@query_handler
def list_projects(request: ListProjects, site: Site) -> list:
    """Return projects: recent ones first, then the rest."""
    recent = list(site.client.get(f"{API}/project/recent", maxResults=20) or [])
    seen = {p["key"] for p in recent}
    rest = [
        p
        for p in site.client.paged(f"{API}/project/search", limit=200, orderBy="name")
        if p["key"] not in seen
    ]
    return recent + rest


@query_handler
def list_issue_types(request: ListIssueTypes, site: Site) -> list:
    """Return the types a project can create (no subtasks: they need a parent)."""
    project = site.client.get(f"{API}/project/{request.project}")
    types = project.get("issueTypes") or site.client.get(
        f"{API}/issuetype/project", projectId=project["id"]
    )
    return [t for t in types if not t.get("subtask")]


# ── commands ─────────────────────────────────────────────────────────────────


@command_handler
def transition_issue(request: TransitionIssue, site: Site) -> str:
    """Apply the transition, with an optional comment."""
    body: dict[str, Any] = {"transition": {"id": request.transition_id}}
    if request.comment:
        body["update"] = {"comment": [{"add": {"body": adf.to_adf(request.comment)}}]}
    site.client.post(f"{API}/issue/{request.key}/transitions", body)
    return request.status


@command_handler
def assign_issue(request: AssignIssue, site: Site) -> None:
    """Set or clear the assignee."""
    site.client.put(f"{API}/issue/{request.key}/assignee", {"accountId": request.account_id})


@command_handler
def comment_on_issue(request: CommentOnIssue, site: Site) -> str:
    """Add the comment."""
    created = site.client.post(
        f"{API}/issue/{request.key}/comment", {"body": adf.to_adf(request.body)}
    )
    return str((created or {}).get("id", ""))


@command_handler
def update_issue(request: UpdateIssue, site: Site) -> None:
    """Set fields and change labels in one edit."""
    body: dict[str, Any] = {}
    if request.fields:
        body["fields"] = dict(request.fields)
    labels = [{"add": label} for label in request.add_labels]
    labels += [{"remove": label} for label in request.remove_labels]
    if labels:
        body["update"] = {"labels": labels}
    if body:
        site.client.put(f"{API}/issue/{request.key}", body)


@command_handler
def create_issue(request: CreateIssue, site: Site) -> str:
    """Create the issue."""
    fields: dict[str, Any] = {
        "project": {"key": request.project},
        "issuetype": {"name": request.issue_type},
        "summary": request.summary.strip(),
    }
    if request.description.strip():
        fields["description"] = adf.to_adf(request.description)
    if request.assign_to_me:
        fields["assignee"] = {"accountId": site.me}
    if request.labels:
        fields["labels"] = list(request.labels)
    created = site.client.post(f"{API}/issue", {"fields": fields})
    return str(created["key"])


@command_handler
def watch_issue(request: WatchIssue, site: Site) -> None:
    """Add or remove the user as a watcher."""
    if request.watch:
        site.client.post(f"{API}/issue/{request.key}/watchers", site.me)
    else:
        site.client.delete(f"{API}/issue/{request.key}/watchers", accountId=site.me)
