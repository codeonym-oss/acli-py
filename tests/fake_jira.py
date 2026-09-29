"""A small, stateful stand-in for Jira Cloud's REST API (platform v3 + Agile 1.0).

It keeps issues, comments, links, filters, boards and sprints in memory, so tests can run a
real `acli-py` command over real HTTP and then look at what changed. Every request is recorded in
`FakeJira.log`, which is how the tests prove that a dry run sends no writes.

JQL is only roughly understood: `project`, `key in`, `labels`, `status`, `assignee =
currentUser()` and `sprint` narrow the result; anything else matches every issue.
All people and projects are fictional.
"""

from __future__ import annotations

import base64
import copy
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

EMAIL = "dev@example.com"
TOKEN = "good-token"

ALICE = {
    "accountId": "70121:11111111-aaaa-4aaa-8aaa-111111111111",
    "displayName": "Alice Martin",
    "emailAddress": EMAIL,
    "accountType": "atlassian",
    "active": True,
    "timeZone": "Europe/Paris",
}
BOB = {
    "accountId": "70121:22222222-bbbb-4bbb-8bbb-222222222222",
    "displayName": "Bob Jensen",
    "emailAddress": "bob@example.com",
    "accountType": "atlassian",
    "active": True,
}
CAROL = {
    "accountId": "70121:33333333-cccc-4ccc-8ccc-333333333333",
    "displayName": "Carol Jensen",
    "emailAddress": "carol@example.com",
    "accountType": "atlassian",
    "active": True,
}
USERS = [ALICE, BOB, CAROL]

STATUSES = {
    "1": {"id": "1", "name": "To Do", "statusCategory": {"key": "new", "name": "To Do"}},
    "3": {
        "id": "3",
        "name": "In Progress",
        "statusCategory": {"key": "indeterminate", "name": "In Progress"},
    },
    "10001": {"id": "10001", "name": "Done", "statusCategory": {"key": "done", "name": "Done"}},
}
TRANSITIONS = [("11", "Reopen", "1"), ("21", "Start work", "3"), ("31", "Finish", "10001")]
ISSUE_TYPES = {
    "Task": {"id": "10001", "name": "Task", "subtask": False, "hierarchyLevel": 0},
    "Bug": {"id": "10002", "name": "Bug", "subtask": False, "hierarchyLevel": 0},
    "Story": {"id": "10003", "name": "Story", "subtask": False, "hierarchyLevel": 0},
    "Epic": {"id": "10004", "name": "Epic", "subtask": False, "hierarchyLevel": 1},
    "Subtask": {"id": "10005", "name": "Subtask", "subtask": True, "hierarchyLevel": -1},
}
PRIORITIES = [
    {"id": "2", "name": "High"},
    {"id": "3", "name": "Medium"},
    {"id": "4", "name": "Low"},
]
CF = "com.atlassian.jira.plugin.system.customfieldtypes:"
FIELDS = [
    {"id": "summary", "name": "Summary", "custom": False, "schema": {"type": "string"}},
    {"id": "description", "name": "Description", "custom": False, "schema": {"type": "string"}},
    {"id": "labels", "name": "Labels", "custom": False, "schema": {"type": "array", "items": "string"}},
    {"id": "assignee", "name": "Assignee", "custom": False, "schema": {"type": "user"}},
    {"id": "priority", "name": "Priority", "custom": False, "schema": {"type": "priority"}},
    {"id": "duedate", "name": "Due date", "custom": False, "schema": {"type": "date"}},
    {
        "id": "customfield_10016",
        "name": "Story point estimate",
        "custom": True,
        "clauseNames": ["cf[10016]", "Story point estimate"],
        "schema": {"type": "number", "custom": CF + "float"},
    },
    {
        "id": "customfield_10020",
        "name": "Team",
        "custom": True,
        "schema": {"type": "option", "custom": CF + "select"},
    },
    {
        "id": "customfield_10030",
        "name": "Notes",
        "custom": True,
        "schema": {"type": "string", "custom": CF + "textarea"},
    },
    {
        "id": "customfield_10040",
        "name": "Reviewers",
        "custom": True,
        "schema": {"type": "array", "items": "user", "custom": CF + "multiuserpicker"},
    },
]  # fmt: skip
LINK_TYPES = [
    {"id": "1000", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
    {"id": "1001", "name": "Cloners", "inward": "is cloned by", "outward": "clones"},
    {"id": "1002", "name": "Duplicate", "inward": "is duplicated by", "outward": "duplicates"},
    {"id": "1003", "name": "Relates", "inward": "relates to", "outward": "relates to"},
]

DOC = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Steps to reproduce."}]},
        {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Open login"}]}
                    ],
                }
            ],
        },
    ],
}


class NotFoundError(Exception):
    """The fake answers 404."""


class BadRequestError(Exception):
    """The fake answers 400."""


class FakeJira:
    """The in-memory site state and request log."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.log: list[tuple[str, str, Any]] = []
        self.fail_next: list[int] = []
        self.reset()

    # ── state ────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Put the site back to its initial state."""
        with self.lock:
            self.log.clear()
            self.fail_next.clear()
            self.next_id = 20000
            self.projects = {
                "DEMO": {"id": "10000", "key": "DEMO", "name": "Demo", "projectTypeKey": "software",
                         "style": "classic", "lead": ALICE, "components": [{"id": "1", "name": "API"}],
                         "versions": [{"id": "5", "name": "2.4", "released": False}]},
                "OPS": {"id": "10001", "key": "OPS", "name": "Operations",
                        "projectTypeKey": "business", "style": "classic", "lead": BOB,
                        "components": [], "versions": []},
            }  # fmt: skip
            self.issues: dict[str, dict] = {}
            self.counters = {"DEMO": 0, "OPS": 0}
            self.links: dict[str, dict] = {}
            self.filters = {
                "10100": {"id": "10100", "name": "My open work", "owner": ALICE,
                          "jql": "project = DEMO AND assignee = currentUser()",
                          "favourite": True, "sharePermissions": [],
                          "columns": ["issuekey", "summary"]},
            }  # fmt: skip
            self.boards = {
                "1": {"id": 1, "name": "DEMO board", "type": "scrum",
                      "location": {"projectKey": "DEMO", "displayName": "Demo (DEMO)"}},
            }  # fmt: skip
            self.sprints = {
                "7": {"id": 7, "name": "Sprint 7", "state": "active", "originBoardId": 1,
                      "startDate": "2026-09-21T09:00:00.000Z", "endDate": "2026-10-05T17:00:00.000Z",
                      "goal": "Ship login"},
                "8": {"id": 8, "name": "Sprint 8", "state": "future", "originBoardId": 1},
            }  # fmt: skip
            self.trashed_fields: set[str] = set()
            self.custom_fields: list[dict] = []
            self.blobs: dict[str, bytes] = {}
            self.add_issue("DEMO", "Login fails on Safari", "Bug", assignee=ALICE,
                           labels=["web"], description=DOC, sprint=7, points=3)  # fmt: skip
            self.add_issue("DEMO", "Write release notes", "Task", assignee=BOB, labels=["docs"])
            self.add_issue("DEMO", "Speed up search", "Story", status="3", sprint=7)
            self.add_issue("OPS", "Rotate certificates", "Task", assignee=ALICE)
            self.link("Blocks", "DEMO-1", "DEMO-3")
            self.issues["DEMO-1"]["comments"].append(
                self.comment(BOB, "Seen on **Safari 18** too.")
            )

    def new_id(self) -> str:
        """Return a fresh id."""
        self.next_id += 1
        return str(self.next_id)

    def add_issue(
        self,
        project: str,
        summary: str,
        kind: str = "Task",
        *,
        assignee: dict | None = None,
        labels: list[str] | None = None,
        description: Any = None,
        status: str = "1",
        sprint: int | None = None,
        points: float | None = None,
        extra: dict | None = None,
    ) -> dict:
        """Add an issue and return it."""
        self.counters[project] += 1
        key = f"{project}-{self.counters[project]}"
        fields = {
            "summary": summary,
            "project": {"id": self.projects[project]["id"], "key": project},
            "issuetype": ISSUE_TYPES[kind],
            "status": STATUSES[status],
            "priority": PRIORITIES[1],
            "assignee": assignee,
            "reporter": ALICE,
            "labels": labels or [],
            "components": [],
            "fixVersions": [],
            "description": description,
            "created": "2026-09-22T10:00:00.000+0200",
            "updated": "2026-09-23T11:30:00.000+0200",
            "duedate": None,
            "resolution": None,
            "parent": None,
            "customfield_10016": points,
            **(extra or {}),
        }
        issue = {
            "id": self.new_id(),
            "key": key,
            "fields": fields,
            "comments": [],
            "worklogs": [],
            "watchers": [ALICE],
            "attachments": [],
            "archived": False,
            "sprint": sprint,
        }
        self.issues[key] = issue
        return issue

    def comment(self, author: dict, text: str) -> dict:
        """Return a new comment."""
        from acli_py.domain.adf import to_adf

        return {
            "id": self.new_id(),
            "author": author,
            "body": to_adf(text),
            "created": "2026-09-24T09:15:00.000+0200",
            "updated": "2026-09-24T09:15:00.000+0200",
        }

    def link(self, type_name: str, outward: str, inward: str) -> str:
        """Link `outward` <type's outward phrase> `inward`; return the link id."""
        link_id = self.new_id()
        self.links[link_id] = {"type": type_name, "outward": outward, "inward": inward}
        return link_id

    def issue(self, key: str) -> dict:
        """Return an issue by key or id, or raise NotFoundError."""
        key = key.upper()
        if key in self.issues:
            return self.issues[key]
        for issue in self.issues.values():
            if issue["id"] == key:
                return issue
        raise NotFoundError(f"Issue does not exist or you do not have permission to see it: {key}")

    def writes(self) -> list[tuple[str, str, Any]]:
        """Return the logged requests that change something."""
        read_posts = (
            "/rest/api/3/search/jql",
            "/rest/api/3/search/approximate-count",
            "/rest/api/3/jql/parse",
        )
        return [
            entry
            for entry in self.log
            if entry[0] not in ("GET", "HEAD")
            and not (entry[0] == "POST" and entry[1] in read_posts)
        ]

    # ── rendering ────────────────────────────────────────────────────────────

    def render(self, issue: dict, fields: list[str] | None = None) -> dict:
        """Return the issue as Jira's JSON, with only `fields` when given."""
        data = copy.deepcopy(issue["fields"])
        data["subtasks"] = [
            {"key": i["key"], "fields": {"summary": i["fields"]["summary"],
                                         "status": i["fields"]["status"]}}
            for i in self.issues.values()
            if (i["fields"].get("parent") or {}).get("key") == issue["key"]
        ]  # fmt: skip
        data["issuelinks"] = self.issue_links(issue["key"])
        data["comment"] = {"comments": issue["comments"], "total": len(issue["comments"])}
        data["attachment"] = issue["attachments"]
        if fields and "*all" not in fields and "*navigable" not in fields:
            data = {k: v for k, v in data.items() if k in fields}
        return {"id": issue["id"], "key": issue["key"], "fields": data}

    def issue_links(self, key: str) -> list[dict]:
        """Return an issue's links as Jira shows them on that issue."""
        result = []
        for link_id, link in self.links.items():
            kind = next(t for t in LINK_TYPES if t["name"] == link["type"])
            if link["outward"] == key:
                other, side = link["inward"], "outwardIssue"
            elif link["inward"] == key:
                other, side = link["outward"], "inwardIssue"
            else:
                continue
            target = self.issues.get(other)
            summary = target["fields"]["summary"] if target else ""
            status = target["fields"]["status"] if target else None
            result.append(
                {"id": link_id, "type": kind,
                 side: {"key": other, "fields": {"summary": summary, "status": status}}}
            )  # fmt: skip
        return result

    # ── JQL, roughly ─────────────────────────────────────────────────────────

    def matches(self, jql: str) -> list[dict]:
        """Return the issues a JQL query selects (a rough reading, see the module doc)."""
        where = re.split(r"(?i)\border\s+by\b", jql)[0]
        found = [i for i in self.issues.values() if not i["archived"]]
        for m in re.finditer(r'(?i)project\s*=\s*"?(\w+)"?', where):
            found = [i for i in found if i["fields"]["project"]["key"] == m.group(1).upper()]
        if m := re.search(r"(?i)key\s+in\s*\(([^)]*)\)", where):
            keys = {k.strip().strip('"').upper() for k in m.group(1).split(",")}
            found = [i for i in found if i["key"] in keys]
        for m in re.finditer(r'(?i)labels\s*=\s*"?([\w-]+)"?', where):
            found = [i for i in found if m.group(1) in i["fields"]["labels"]]
        for m in re.finditer(r'(?i)\bstatus\s*=\s*"([^"]+)"', where):
            found = [
                i for i in found if i["fields"]["status"]["name"].lower() == m.group(1).lower()
            ]
        if re.search(r"(?i)assignee\s*=\s*currentUser\(\)", where):
            found = [
                i
                for i in found
                if (i["fields"]["assignee"] or {}).get("accountId") == ALICE["accountId"]
            ]
        if m := re.search(r'(?i)assignee\s*=\s*"([^"]+:[^"]+)"', where):
            found = [
                i for i in found if (i["fields"]["assignee"] or {}).get("accountId") == m.group(1)
            ]
        if m := re.search(r"(?i)sprint\s*=\s*(\d+)", where):
            found = [i for i in found if i["sprint"] == int(m.group(1))]
        if m := re.search(r'(?i)\btext\s*~\s*"([^"]+)"', where):
            words = m.group(1).lower().split()
            found = [i for i in found if all(w in i["fields"]["summary"].lower() for w in words)]
        if m := re.search(r"(?i)statusCategory\s*(!?=)\s*Done", where):
            done = m.group(1) == "="
            found = [
                i
                for i in found
                if (i["fields"]["status"]["statusCategory"]["key"] == "done") == done
            ]
        return found

    # ── writes, shared by several routes ─────────────────────────────────────

    def apply_fields(self, issue: dict, fields: dict) -> None:
        """Store fields sent by a create or edit, as Jira would show them."""
        target = issue["fields"]
        for name, value in fields.items():
            if name == "issuetype":
                target[name] = ISSUE_TYPES.get(value.get("name")) or next(
                    (t for t in ISSUE_TYPES.values() if t["id"] == value.get("id")), None
                )
                if target[name] is None:
                    raise BadRequestError(
                        json.dumps({"errors": {"issuetype": "Specify a valid issue type"}})
                    )
            elif name in ("assignee", "reporter"):
                target[name] = (
                    next((u for u in USERS if u["accountId"] == value.get("accountId")), None)
                    if value
                    else None
                )
            elif name == "priority":
                target[name] = next(
                    (
                        p
                        for p in PRIORITIES
                        if p["name"] == value.get("name") or p["id"] == value.get("id")
                    ),
                    None,
                )
            elif name == "parent":
                target[name] = {
                    "key": value["key"],
                    "fields": {"summary": self.issue(value["key"])["fields"]["summary"]},
                }
            elif name == "project":
                continue
            elif name.startswith("customfield_") and not any(f["id"] == name for f in FIELDS):
                raise BadRequestError(json.dumps({"errors": {name: "Field does not exist"}}))
            else:
                target[name] = value

    def create_issue(self, body: dict) -> dict:
        """Create an issue from a POST /issue body."""
        fields = body.get("fields", {})
        project = (fields.get("project") or {}).get("key")
        if project not in self.projects:
            raise BadRequestError(json.dumps({"errors": {"project": "valid project is required"}}))
        if not fields.get("summary"):
            raise BadRequestError(
                json.dumps({"errors": {"summary": "You must specify a summary."}})
            )
        kind = (fields.get("issuetype") or {}).get("name", "Task")
        if kind not in ISSUE_TYPES:
            raise BadRequestError(
                json.dumps({"errors": {"issuetype": "Specify a valid issue type"}})
            )
        issue = self.add_issue(project, fields["summary"], kind)
        self.apply_fields(issue, {k: v for k, v in fields.items() if k != "issuetype"})
        return {"id": issue["id"], "key": issue["key"], "self": f"/rest/api/3/issue/{issue['id']}"}


# ── HTTP ─────────────────────────────────────────────────────────────────────

Route = tuple[str, re.Pattern[str], Any]
ROUTES: list[Route] = []


def route(method: str, pattern: str):
    """Register a handler for METHOD and a path regex."""

    def register(func):
        ROUTES.append((method, re.compile(f"^{pattern}$"), func))
        return func

    return register


def page(items: list, q: dict, key: str = "values") -> dict:
    """Return a startAt/maxResults page."""
    start = int(q.get("startAt", ["0"])[0])
    size = int(q.get("maxResults", ["50"])[0])
    chunk = items[start : start + size]
    return {key: chunk, "startAt": start, "maxResults": size, "total": len(items),
            "isLast": start + size >= len(items)}  # fmt: skip


A = "/rest/api/3"
G = "/rest/agile/1.0"


@route("GET", f"{A}/myself")
def _myself(jira, q, body):
    return ALICE


@route("GET", f"{A}/serverInfo")
def _server(jira, q, body):
    return {"baseUrl": "http://fake", "deploymentType": "Cloud"}


@route("POST", f"{A}/search/jql")
def _search(jira, q, body):
    found = jira.matches(body.get("jql", ""))
    start = int(body.get("nextPageToken") or 0)
    size = int(body.get("maxResults", 50))
    chunk = found[start : start + size]
    fields = body.get("fields") or []
    result: dict[str, Any] = {"issues": [jira.render(i, fields) for i in chunk]}
    if start + size < len(found):
        result["nextPageToken"] = str(start + size)
    else:
        result["isLast"] = True
    return result


@route("POST", f"{A}/search/approximate-count")
def _count(jira, q, body):
    return {"count": len(jira.matches(body.get("jql", "")))}


@route("GET", f"{A}/issue/(?P<key>[^/]+)")
def _issue(jira, q, body, key):
    fields = q.get("fields", [""])[0].split(",") if "fields" in q else None
    data = jira.render(jira.issue(key), fields)
    if "names" in q.get("expand", [""])[0]:
        data["names"] = {f["id"]: f["name"] for f in FIELDS}
    return data


@route("POST", f"{A}/issue")
def _create(jira, q, body):
    return 201, jira.create_issue(body)


@route("PUT", f"{A}/issue/(?P<key>[A-Z]+-\\d+|\\d+)")
def _edit(jira, q, body, key):
    issue = jira.issue(key)
    jira.apply_fields(issue, body.get("fields", {}))
    for op in (body.get("update") or {}).get("labels", []):
        labels = issue["fields"]["labels"]
        if "add" in op and op["add"] not in labels:
            labels.append(op["add"])
        if "remove" in op and op["remove"] in labels:
            labels.remove(op["remove"])
    return 204, None


@route("DELETE", f"{A}/issue/(?P<key>[A-Z]+-\\d+|\\d+)")
def _delete(jira, q, body, key):
    issue = jira.issue(key)
    subtasks = [
        i
        for i in jira.issues.values()
        if (i["fields"].get("parent") or {}).get("key") == issue["key"]
    ]
    if subtasks and q.get("deleteSubtasks", ["false"])[0] != "true":
        raise BadRequestError(json.dumps({"errorMessages": ["The issue has subtasks."]}))
    for gone in [issue, *subtasks]:
        del jira.issues[gone["key"]]
    return 204, None


@route("PUT", f"{A}/issue/(?P<key>[^/]+)/assignee")
def _assign(jira, q, body, key):
    issue = jira.issue(key)
    account = body.get("accountId")
    if account == "-1":
        issue["fields"]["assignee"] = BOB  # DEMO's default assignee
    else:
        issue["fields"]["assignee"] = next((u for u in USERS if u["accountId"] == account), None)
    return 204, None


@route("GET", f"{A}/issue/(?P<key>[^/]+)/transitions")
def _transitions(jira, q, body, key):
    current = jira.issue(key)["fields"]["status"]["id"]
    return {"transitions": [
        {"id": tid, "name": name, "to": STATUSES[to]} for tid, name, to in TRANSITIONS if to != current
    ]}  # fmt: skip


@route("POST", f"{A}/issue/(?P<key>[^/]+)/transitions")
def _transition(jira, q, body, key):
    issue = jira.issue(key)
    tid = body["transition"]["id"]
    target = next((to for t, _, to in TRANSITIONS if t == tid), None)
    if target is None or target == issue["fields"]["status"]["id"]:
        raise BadRequestError(json.dumps({"errorMessages": ["Transition id is not valid"]}))
    issue["fields"]["status"] = STATUSES[target]
    for name, value in (body.get("fields") or {}).items():
        issue["fields"][name] = value
    for op in (body.get("update") or {}).get("comment", []):
        comment = jira.comment(ALICE, "")
        comment["body"] = op["add"]["body"]
        issue["comments"].append(comment)
    return 204, None


@route("PUT", f"{A}/issue/(?P<which>archive|unarchive)")
def _archive(jira, q, body, which):
    errors: dict[str, Any] = {}
    for key in body.get("issueIdsOrKeys", []):
        if key.upper() in jira.issues:
            jira.issues[key.upper()]["archived"] = which == "archive"
        else:
            errors.setdefault(
                "issueNotFound", {"count": 0, "issueIdsOrKeys": [], "message": "missing"}
            )
            errors["issueNotFound"]["count"] += 1
            errors["issueNotFound"]["issueIdsOrKeys"].append(key)
    return {
        "errors": errors,
        "numberOfIssuesUpdated": len(body.get("issueIdsOrKeys", [])) - len(errors),
    }


@route("GET", f"{A}/issue/(?P<key>[^/]+)/comment")
def _comments(jira, q, body, key):
    comments = list(jira.issue(key)["comments"])
    if q.get("orderBy", [""])[0].startswith("-"):
        comments.reverse()
    return page(comments, q, "comments")


@route("POST", f"{A}/issue/(?P<key>[^/]+)/comment")
def _add_comment(jira, q, body, key):
    comment = jira.comment(ALICE, "")
    comment["body"] = body["body"]
    if body.get("visibility"):
        comment["visibility"] = body["visibility"]
    jira.issue(key)["comments"].append(comment)
    return 201, comment


def _find_comment(jira, key, cid):
    for comment in jira.issue(key)["comments"]:
        if comment["id"] == cid:
            return comment
    raise NotFoundError("Can not find a comment for the id")


@route("GET", f"{A}/issue/(?P<key>[^/]+)/comment/(?P<cid>\\d+)")
def _get_comment(jira, q, body, key, cid):
    return _find_comment(jira, key, cid)


@route("PUT", f"{A}/issue/(?P<key>[^/]+)/comment/(?P<cid>\\d+)")
def _edit_comment(jira, q, body, key, cid):
    comment = _find_comment(jira, key, cid)
    comment["body"] = body["body"]
    comment["updated"] = "2026-09-25T10:00:00.000+0200"
    return comment


@route("DELETE", f"{A}/issue/(?P<key>[^/]+)/comment/(?P<cid>\\d+)")
def _delete_comment(jira, q, body, key, cid):
    jira.issue(key)["comments"].remove(_find_comment(jira, key, cid))
    return 204, None


@route("POST", f"{A}/issue/(?P<key>[^/]+)/remotelink")
def _remote_link(jira, q, body, key):
    issue = jira.issue(key)
    issue.setdefault("remote_links", []).append(body["object"])
    return 201, {"id": int(jira.new_id())}


@route("GET", f"{A}/issueLinkType")
def _link_types(jira, q, body):
    return {"issueLinkTypes": LINK_TYPES}


@route("POST", f"{A}/issueLink")
def _add_link(jira, q, body):
    name = body["type"]["name"]
    if not any(t["name"] == name for t in LINK_TYPES):
        raise NotFoundError(f"No issue link type with name '{name}' found.")
    outward, inward = (
        jira.issue(body["outwardIssue"]["key"]),
        jira.issue(body["inwardIssue"]["key"]),
    )
    jira.link(name, outward["key"], inward["key"])
    if body.get("comment"):
        comment = jira.comment(ALICE, "")
        comment["body"] = body["comment"]["body"]
        outward["comments"].append(comment)
    return 201, None


@route("DELETE", f"{A}/issueLink/(?P<lid>\\d+)")
def _delete_link(jira, q, body, lid):
    if lid not in jira.links:
        raise NotFoundError("No issue link with id")
    del jira.links[lid]
    return 204, None


@route("POST", f"{A}/issue/(?P<key>[^/]+)/attachments")
def _attach(jira, q, body, key):
    issue = jira.issue(key)
    attachment = {"id": jira.new_id(), "filename": body["filename"], "size": len(body["content"]),
                  "mimeType": "text/plain", "author": ALICE,
                  "created": "2026-09-25T10:00:00.000+0200"}  # fmt: skip
    jira.blobs[attachment["id"]] = body["content"]
    issue["attachments"].append(attachment)
    return [attachment]


def _find_attachment(jira, aid):
    for issue in jira.issues.values():
        for attachment in issue["attachments"]:
            if attachment["id"] == aid:
                return issue, attachment
    raise NotFoundError("attachment not found")


@route("GET", f"{A}/attachment/(?P<aid>\\d+)")
def _attachment_meta(jira, q, body, aid):
    return _find_attachment(jira, aid)[1]


@route("GET", f"{A}/attachment/content/(?P<aid>\\d+)")
def _attachment_content(jira, q, body, aid):
    _find_attachment(jira, aid)
    return "raw", jira.blobs[aid]


@route("DELETE", f"{A}/attachment/(?P<aid>\\d+)")
def _attachment_delete(jira, q, body, aid):
    issue, attachment = _find_attachment(jira, aid)
    issue["attachments"].remove(attachment)
    return 204, None


@route("GET", f"{A}/issue/(?P<key>[^/]+)/watchers")
def _watchers(jira, q, body, key):
    watchers = jira.issue(key)["watchers"]
    return {"watchCount": len(watchers), "isWatching": ALICE in watchers, "watchers": watchers}


@route("POST", f"{A}/issue/(?P<key>[^/]+)/watchers")
def _watch(jira, q, body, key):
    user = next(u for u in USERS if u["accountId"] == body)
    watchers = jira.issue(key)["watchers"]
    if user not in watchers:
        watchers.append(user)
    return 204, None


@route("DELETE", f"{A}/issue/(?P<key>[^/]+)/watchers")
def _unwatch(jira, q, body, key):
    issue = jira.issue(key)
    issue["watchers"] = [u for u in issue["watchers"] if u["accountId"] != q["accountId"][0]]
    return 204, None


@route("GET", f"{A}/issue/(?P<key>[^/]+)/worklog")
def _worklogs(jira, q, body, key):
    return page(jira.issue(key)["worklogs"], q, "worklogs")


@route("POST", f"{A}/issue/(?P<key>[^/]+)/worklog")
def _add_worklog(jira, q, body, key):
    log = {"id": jira.new_id(), "author": ALICE, "timeSpent": body["timeSpent"],
           "started": body.get("started", "2026-09-25T09:00:00.000+0200"),
           "comment": body.get("comment")}  # fmt: skip
    jira.issue(key)["worklogs"].append(log)
    return 201, log


@route("DELETE", f"{A}/issue/(?P<key>[^/]+)/worklog/(?P<wid>\\d+)")
def _delete_worklog(jira, q, body, key, wid):
    issue = jira.issue(key)
    issue["worklogs"] = [w for w in issue["worklogs"] if w["id"] != wid]
    return 204, None


@route("GET", f"{A}/user/search")
def _user_search(jira, q, body):
    needle = q.get("query", [""])[0].lower()
    return [u for u in USERS if needle in u["displayName"].lower() or needle in u["emailAddress"]]


@route("GET", f"{A}/user/assignable/search")
def _assignable(jira, q, body):
    jira.issue(q["issueKey"][0])
    return _user_search(jira, q, body)


@route("GET", f"{A}/jql/autocompletedata")
def _jql_reference(jira, q, body):
    eq = ["=", "!=", "in", "not in", "is", "is not"]
    names = ["project", "status", "assignee", "reporter", "issuetype", "priority", "labels",
             "sprint", "key", "created", "updated"]  # fmt: skip
    fields = [{"value": n, "displayName": n, "operators": eq, "orderable": "true",
               "searchable": "true", "types": []} for n in names]  # fmt: skip
    fields.append({"value": "summary", "displayName": "summary", "operators": ["~", "!~"],
                   "orderable": "true", "types": []})  # fmt: skip
    fields.append({"value": "cf[10016]", "displayName": "Story point estimate - cf[10016]",
                   "cfid": "cf[10016]", "operators": ["=", ">", "<"], "orderable": "true",
                   "types": ["java.lang.Number"]})  # fmt: skip
    functions = [{"value": "currentUser()", "displayName": "currentUser()", "isList": "false"},
                 {"value": "openSprints()", "displayName": "openSprints()", "isList": "true"}]  # fmt: skip
    return {"visibleFieldNames": fields, "visibleFunctionNames": functions,
            "jqlReservedWords": ["and", "or", "in"]}  # fmt: skip


@route("GET", f"{A}/jql/autocompletedata/suggestions")
def _jql_suggestions(jira, q, body):
    name = q.get("fieldName", [""])[0].lower()
    typed = q.get("fieldValue", [""])[0].lower()
    if name == "status":
        values = [(s["name"], s["name"]) for s in STATUSES.values()]
    elif name == "project":
        values = [(k, f"{p['name']} ({k})") for k, p in jira.projects.items()]
    elif name == "issuetype":
        values = [(t, t) for t in ISSUE_TYPES]
    elif name == "priority":
        values = [(p["name"], p["name"]) for p in PRIORITIES]
    elif name == "labels":
        labels = sorted({label for i in jira.issues.values() for label in i["fields"]["labels"]})
        values = [(label, label) for label in labels]
    elif name in ("assignee", "reporter"):
        values = [(u["accountId"], u["displayName"]) for u in USERS]
    else:
        values = []
    hits = [(v, d) for v, d in values if typed in v.lower() or typed in d.lower()]
    return {"results": [{"value": v, "displayName": d} for v, d in hits]}


@route("POST", f"{A}/jql/parse")
def _jql_parse(jira, q, body):
    results = []
    for query in body.get("queries", []):
        errors = []
        if query.count("(") != query.count(")") or query.count('"') % 2:
            errors.append("Error in the JQL Query: the query is not complete.")
        if m := re.search(r"(?i)\b(nosuch\w*)\s*(=|~|in)", query):
            errors.append(f"Field '{m.group(1)}' does not exist or you do not have permission.")
        results.append({"query": query, "errors": errors})
    return {"queries": results}


@route("GET", f"{A}/issue/picker")
def _picker(jira, q, body):
    typed = q.get("query", [""])[0].lower()
    hits = [
        {"key": i["key"], "summaryText": i["fields"]["summary"]}
        for i in jira.issues.values()
        if i["key"].lower().startswith(typed) or typed in i["fields"]["summary"].lower()
    ]
    return {"sections": [{"label": "History Search", "issues": hits}]}


ROUTES.insert(0, ROUTES.pop())  # before GET /issue/{key}, which would take "picker" for a key


@route("GET", f"{A}/user")
def _user(jira, q, body):
    account = q["accountId"][0]
    for user in USERS:
        if user["accountId"] == account:
            return {**user, "groups": {"items": [{"name": "jira-users"}]}}
    raise NotFoundError("user not found")


@route("GET", f"{A}/field")
def _fields(jira, q, body):
    return [f for f in FIELDS + jira.custom_fields if f["id"] not in jira.trashed_fields]


@route("POST", f"{A}/field")
def _create_field(jira, q, body):
    field = {"id": f"customfield_{jira.new_id()}", "name": body["name"], "custom": True,
             "schema": {"type": "string", "custom": body["type"]}}  # fmt: skip
    jira.custom_fields.append(field)
    return 201, field


@route("PUT", f"{A}/field/(?P<fid>[^/]+)")
def _update_field(jira, q, body, fid):
    for field in FIELDS + jira.custom_fields:
        if field["id"] == fid:
            field.update({k: v for k, v in body.items() if k == "name"})
            return 204, None
    raise NotFoundError("field not found")


@route("POST", f"{A}/field/(?P<fid>[^/]+)/(?P<action>trash|restore)")
def _trash_field(jira, q, body, fid, action):
    (jira.trashed_fields.add if action == "trash" else jira.trashed_fields.discard)(fid)
    return 204, None


@route("GET", f"{A}/project/search")
def _projects(jira, q, body):
    query = q.get("query", [""])[0].lower()
    found = [
        p for p in jira.projects.values() if query in p["key"].lower() or query in p["name"].lower()
    ]
    return page(found, q)


@route("GET", f"{A}/project/recent")
def _recent(jira, q, body):
    return list(jira.projects.values())[:1]


def _project(jira, key):
    if key.upper() not in jira.projects:
        raise NotFoundError(f"No project could be found with key '{key}'.")
    return jira.projects[key.upper()]


@route("GET", f"{A}/project/(?P<key>[^/]+)")
def _get_project(jira, q, body, key):
    project = _project(jira, key)
    return {**project, "issueTypes": list(ISSUE_TYPES.values())}


@route("POST", f"{A}/project")
def _create_project(jira, q, body):
    for required in ("key", "name", "projectTypeKey", "leadAccountId"):
        if not body.get(required):
            raise BadRequestError(json.dumps({"errors": {required: "required"}}))
    if body.get("projectTemplateKey") and body.get("workflowScheme"):
        raise BadRequestError(json.dumps({"errorMessages": ["template or schemes, not both"]}))
    project = {"id": jira.new_id(), "key": body["key"], "name": body["name"],
               "projectTypeKey": body["projectTypeKey"], "style": "classic", "lead": ALICE,
               "components": [], "versions": [],
               "schemes": {k: v for k, v in body.items() if k.endswith("Scheme")}}  # fmt: skip
    jira.projects[body["key"]] = project
    jira.counters[body["key"]] = 0
    return 201, {"id": project["id"], "key": project["key"]}


@route(
    "GET",
    f"{A}/project/(?P<key>[^/]+)/(?P<kind>permissionscheme|notificationscheme|issuesecuritylevelscheme)",
)
def _project_scheme(jira, q, body, key, kind):
    if key not in jira.projects:
        raise NotFoundError("no project")
    if kind == "issuesecuritylevelscheme":
        raise NotFoundError("no issue security scheme")
    return {"id": {"permissionscheme": 0, "notificationscheme": 10000}[kind], "name": kind}


@route("GET", f"{A}/(?P<kind>issuetypescheme|issuetypescreenscheme|workflowscheme)/project")
def _schemes_by_project(jira, q, body, kind):
    inner = {"issuetypescheme": "issueTypeScheme", "issuetypescreenscheme": "issueTypeScreenScheme",
             "workflowscheme": "workflowScheme"}[kind]  # fmt: skip
    ids = {"issuetypescheme": "10010", "issuetypescreenscheme": "10020", "workflowscheme": "10030"}
    return {"values": [{inner: {"id": ids[kind]}, "projectIds": q["projectId"]}]}


@route("PUT", f"{A}/project/(?P<key>[^/]+)")
def _update_project(jira, q, body, key):
    project = _project(jira, key)
    project.update({k: v for k, v in body.items() if k in ("name", "description", "url")})
    return project


@route("DELETE", f"{A}/project/(?P<key>[^/]+)")
def _delete_project(jira, q, body, key):
    del jira.projects[_project(jira, key)["key"]]
    return 204, None


@route("POST", f"{A}/project/(?P<key>[^/]+)/(?P<action>archive|restore)")
def _archive_project(jira, q, body, key, action):
    _project(jira, key)["archived"] = action == "archive"
    return 204, None


@route("GET", f"{A}/project/(?P<key>[^/]+)/components")
def _components(jira, q, body, key):
    return _project(jira, key)["components"]


@route("GET", f"{A}/project/(?P<key>[^/]+)/versions")
def _versions(jira, q, body, key):
    return _project(jira, key)["versions"]


@route("GET", f"{A}/project/(?P<key>[^/]+)/role")
def _roles(jira, q, body, key):
    return {"Administrators": "…/10002", "Developers": "…/10001"}


@route("GET", f"{A}/groups/picker")
def _groups(jira, q, body):
    return {"groups": [{"name": "jira-users"}, {"name": "developers"}]}


@route("GET", f"{A}/status")
def _statuses(jira, q, body):
    return list(STATUSES.values())


@route("GET", f"{A}/priority/search")
def _priorities(jira, q, body):
    return page(PRIORITIES, q)


@route("GET", f"{A}/resolution/search")
def _resolutions(jira, q, body):
    return page([{"id": "1", "name": "Done"}, {"id": "2", "name": "Won't Do"}], q)


@route("GET", f"{A}/issuetype")
def _issue_types(jira, q, body):
    return list(ISSUE_TYPES.values())


@route("GET", f"{A}/issuetype/project")
def _project_issue_types(jira, q, body):
    return list(ISSUE_TYPES.values())[:3]


def _filter(jira, fid):
    if fid not in jira.filters:
        raise NotFoundError(f"The selected filter is not available to you: {fid}")
    return jira.filters[fid]


@route("GET", f"{A}/filter/my")
def _my_filters(jira, q, body):
    return [f for f in jira.filters.values() if f["owner"] is ALICE]


@route("GET", f"{A}/filter/favourite")
def _favourite_filters(jira, q, body):
    return [f for f in jira.filters.values() if f["favourite"]]


@route("GET", f"{A}/filter/search")
def _search_filters(jira, q, body):
    name = q.get("filterName", [""])[0].lower()
    return page([f for f in jira.filters.values() if name in f["name"].lower()], q)


@route("GET", f"{A}/filter/(?P<fid>\\d+)")
def _get_filter(jira, q, body, fid):
    return _filter(jira, fid)


@route("POST", f"{A}/filter")
def _create_filter(jira, q, body):
    fid = jira.new_id()
    jira.filters[fid] = {"id": fid, "owner": ALICE, "favourite": False, "sharePermissions": [],
                         "columns": [], **body}  # fmt: skip
    return jira.filters[fid]


@route("PUT", f"{A}/filter/(?P<fid>\\d+)")
def _update_filter(jira, q, body, fid):
    _filter(jira, fid).update(body)
    return _filter(jira, fid)


@route("DELETE", f"{A}/filter/(?P<fid>\\d+)")
def _delete_filter(jira, q, body, fid):
    del jira.filters[_filter(jira, fid)["id"]]
    return 204, None


@route("PUT", f"{A}/filter/(?P<fid>\\d+)/favourite")
def _star(jira, q, body, fid):
    _filter(jira, fid)["favourite"] = True
    return _filter(jira, fid)


@route("DELETE", f"{A}/filter/(?P<fid>\\d+)/favourite")
def _unstar(jira, q, body, fid):
    _filter(jira, fid)["favourite"] = False
    return _filter(jira, fid)


@route("PUT", f"{A}/filter/(?P<fid>\\d+)/owner")
def _owner(jira, q, body, fid):
    _filter(jira, fid)["owner"] = next(u for u in USERS if u["accountId"] == body["accountId"])
    return 204, None


@route("GET", f"{A}/filter/(?P<fid>\\d+)/columns")
def _columns(jira, q, body, fid):
    return [{"value": c, "label": c.title()} for c in _filter(jira, fid)["columns"]]


@route("PUT", f"{A}/filter/(?P<fid>\\d+)/columns")
def _set_columns(jira, q, body, fid):
    _filter(jira, fid)["columns"] = body["columns"]
    return 204, None


@route("DELETE", f"{A}/filter/(?P<fid>\\d+)/columns")
def _reset_columns(jira, q, body, fid):
    _filter(jira, fid)["columns"] = []
    return 204, None


@route("GET", f"{A}/dashboard/search")
def _dashboards(jira, q, body):
    return page([{"id": "10200", "name": "Team health", "owner": ALICE, "isFavourite": True,
                  "view": "http://fake/jira/dashboards/10200"}], q)  # fmt: skip


@route("GET", f"{A}/dashboard/(?P<did>\\d+)")
def _dashboard(jira, q, body, did):
    return {"id": did, "name": "Team health", "owner": ALICE, "view": "http://fake/d"}


# ── agile ────────────────────────────────────────────────────────────────────


def _board(jira, bid):
    if bid not in jira.boards:
        raise NotFoundError(f"Board does not exist: {bid}")
    return jira.boards[bid]


@route("GET", f"{G}/board")
def _boards(jira, q, body):
    return page(list(jira.boards.values()), q)


@route("GET", f"{G}/board/(?P<bid>\\d+)")
def _get_board(jira, q, body, bid):
    return _board(jira, bid)


@route("GET", f"{G}/board/(?P<bid>\\d+)/configuration")
def _board_config(jira, q, body, bid):
    _board(jira, bid)
    return {
        "filter": {"id": "10100"},
        "columnConfig": {"columns": [{"name": "To Do"}, {"name": "Done"}]},
    }


@route("POST", f"{G}/board")
def _create_board(jira, q, body):
    bid = jira.new_id()
    jira.boards[bid] = {"id": int(bid), "name": body["name"], "type": body["type"], "location": {}}
    return 201, jira.boards[bid]


@route("DELETE", f"{G}/board/(?P<bid>\\d+)")
def _delete_board(jira, q, body, bid):
    del jira.boards[str(_board(jira, bid)["id"])]
    return 204, None


@route("GET", f"{G}/board/(?P<bid>\\d+)/project")
def _board_projects(jira, q, body, bid):
    _board(jira, bid)
    return page([jira.projects["DEMO"]], q)


@route("GET", f"{G}/board/(?P<bid>\\d+)/sprint")
def _board_sprints(jira, q, body, bid):
    _board(jira, bid)
    states = q.get("state", [""])[0].split(",") if "state" in q else None
    return page([s for s in jira.sprints.values() if not states or s["state"] in states], q)


@route("GET", f"{G}/board/(?P<bid>\\d+)/backlog")
def _backlog(jira, q, body, bid):
    issues = [
        jira.render(i)
        for i in jira.issues.values()
        if i["sprint"] is None and i["key"].startswith("DEMO")
    ]
    return page(issues, q, "issues")


def _sprint(jira, sid):
    if sid not in jira.sprints:
        raise NotFoundError(f"Sprint does not exist: {sid}")
    return jira.sprints[sid]


@route("GET", f"{G}/sprint/(?P<sid>\\d+)")
def _get_sprint(jira, q, body, sid):
    return _sprint(jira, sid)


@route("POST", f"{G}/sprint")
def _create_sprint(jira, q, body):
    sid = jira.new_id()
    jira.sprints[sid] = {"id": int(sid), "state": "future", **body}
    return 201, jira.sprints[sid]


@route("POST", f"{G}/sprint/(?P<sid>\\d+)")
def _update_sprint(jira, q, body, sid):
    sprint = _sprint(jira, sid)
    if body.get("state") == "active" and not (body.get("startDate") and body.get("endDate")):
        raise BadRequestError(json.dumps({"errorMessages": ["A sprint needs dates to start."]}))
    sprint.update(body)
    return sprint


@route("DELETE", f"{G}/sprint/(?P<sid>\\d+)")
def _delete_sprint(jira, q, body, sid):
    del jira.sprints[str(_sprint(jira, sid)["id"])]
    return 204, None


@route("GET", f"{G}/sprint/(?P<sid>\\d+)/issue")
def _sprint_issues(jira, q, body, sid):
    _sprint(jira, sid)
    return page(
        [jira.render(i) for i in jira.issues.values() if i["sprint"] == int(sid)], q, "issues"
    )


@route("POST", f"{G}/sprint/(?P<sid>\\d+)/issue")
def _move_to_sprint(jira, q, body, sid):
    _sprint(jira, sid)
    for key in body["issues"]:
        jira.issue(key)["sprint"] = int(sid)
    return 204, None


@route("POST", f"{G}/backlog/issue")
def _move_to_backlog(jira, q, body):
    for key in body["issues"]:
        jira.issue(key)["sprint"] = None
    return 204, None


# ── server ───────────────────────────────────────────────────────────────────


class Handler(BaseHTTPRequestHandler):
    """Dispatch requests to the route table."""

    jira: FakeJira

    def log_message(self, format, *args):
        pass

    def _authorized(self) -> bool:
        expected = "Basic " + base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
        return self.headers.get("Authorization") == expected

    def _send(self, status: int, payload: Any = None, raw: bytes | None = None) -> None:
        data = (
            raw if raw is not None else (b"" if payload is None else json.dumps(payload).encode())
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream" if raw else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else b""
        kind = self.headers.get("Content-Type", "")
        if kind.startswith("multipart/form-data"):
            return _multipart(data, kind)
        return json.loads(data) if data else None

    def _handle(self, method: str) -> None:
        url = urlparse(self.path)
        q = parse_qs(url.query)
        body = self._body()
        jira = self.jira
        with jira.lock:
            jira.log.append((method, url.path, body))
            if jira.fail_next:
                self._send(jira.fail_next.pop(0), {"errorMessages": ["try again"]})
                return
        if not self._authorized():
            self._send(401, {"errorMessages": ["Unauthorized"]})
            return
        for verb, pattern, handler in ROUTES:
            if verb == method and (m := pattern.match(url.path)):
                try:
                    with jira.lock:
                        result = handler(jira, q, body, **m.groupdict())
                except NotFoundError as error:
                    self._send(404, {"errorMessages": [str(error)]})
                    return
                except BadRequestError as error:
                    self._send(400, json.loads(str(error)))
                    return
                if isinstance(result, tuple) and result[0] == "raw":
                    self._send(200, raw=result[1])
                elif isinstance(result, tuple):
                    self._send(result[0], result[1])
                else:
                    self._send(200, result)
                return
        self._send(404, {"errorMessages": [f"no fake route for {method} {url.path}"]})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")


def _multipart(data: bytes, kind: str) -> dict:
    boundary = kind.split("boundary=", 1)[1].encode()
    for part in data.split(b"--" + boundary):
        if b"filename=" in part:
            head, _, content = part.partition(b"\r\n\r\n")
            name = re.search(rb'filename="([^"]+)"', head)
            return {"filename": name.group(1).decode() if name else "file", "content": content[:-2]}
    return {}


def start() -> tuple[ThreadingHTTPServer, FakeJira, str]:
    """Start the fake on a free port; return (server, state, base URL)."""
    jira = FakeJira()
    handler = type("BoundHandler", (Handler,), {"jira": jira})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, jira, f"http://127.0.0.1:{server.server_address[1]}"
