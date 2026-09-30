"""The handlers behind each query here: plain functions over the Jira client.

They are sync, so mediary runs each on a worker thread and the UI never blocks on the network.
Their `Site` parameter is supplied by the mediator's resolver.
"""

from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.messages import (
    FindAssignees,
    GetTransitions,
    ListFilters,
    ListIssueTypes,
    ListPriorities,
    ListProjects,
    ValidateJql,
)
from acli_py.application.site import Site
from acli_py.infrastructure.jira.client import API

# ── queries ──────────────────────────────────────────────────────────────────


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
