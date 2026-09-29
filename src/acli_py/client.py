"""A Jira Cloud REST client (platform v3 and Agile 1.0) with retries and a dry-run mode.

In dry-run mode every read still goes to Jira, so commands can resolve their targets and
show real names, but no write leaves the machine: each one is recorded as a `PlannedRequest`,
handed to `on_plan`, and answered with a stand-in response.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

API = "/rest/api/3"
AGILE = "/rest/agile/1.0"
PAGE_SIZE = 50
SEARCH_PAGE_SIZE = 100
TIMEOUT = 30
USER_AGENT = "acli-py"

# POSTs that only read. They run even in dry-run mode.
READ_ONLY_POSTS = (
    f"{API}/search/jql",
    f"{API}/search/approximate-count",
    f"{API}/issue/bulkfetch",
    f"{API}/jql/parse",
)

# A stand-in id for things a dry run pretends to create.
DRY_RUN_ID = "DRY-RUN"


class JiraError(RuntimeError):
    """A Jira request failed."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AuthError(JiraError):
    """Jira rejected the credentials."""


class NotFoundError(JiraError):
    """The resource does not exist, or the account cannot see it."""


@dataclass
class PlannedRequest:
    """A write that a dry run did not send."""

    method: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)
    body: Any = None
    files: list[str] = field(default_factory=list)


def normalize_url(url: str) -> str:
    """Return the site URL with a scheme and no trailing slash."""
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def site_host(url: str) -> str:
    """Return the host part of a site URL."""
    return normalize_url(url).split("://", 1)[1].split("/", 1)[0]


class _Retry(Retry):
    """Retry 5xx only for idempotent methods, but 429 for every method.

    A 429 means Jira refused the request without acting on it, so even a POST is safe to
    resend. A 502 after a POST may hide an issue that was created, so it is not retried.
    """

    def is_retry(self, method: str, status_code: int, has_retry_after: bool = False) -> bool:
        if status_code == 429:
            return bool(self.total)
        return super().is_retry(method, status_code, has_retry_after)


class JiraClient:
    """Jira Cloud REST calls, with retries and an optional dry run."""

    def __init__(
        self,
        base_url: str,
        email: str,
        token: str,
        *,
        dry_run: bool = False,
        on_response: Callable[[requests.Response], None] | None = None,
        on_plan: Callable[[PlannedRequest], None] | None = None,
        retries: int = 5,
    ) -> None:
        self.base_url = normalize_url(base_url)
        self.dry_run = dry_run
        self.planned: list[PlannedRequest] = []
        self.on_plan = on_plan
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(email, token)
        self.session.headers.update({"Accept": "application/json", "User-Agent": USER_AGENT})
        retry = _Retry(
            total=retries,
            backoff_factor=1,
            status_forcelist=(500, 502, 503, 504),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        if on_response:
            self.session.hooks["response"].append(lambda resp, *args, **kwargs: on_response(resp))

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()

    # ── transport ────────────────────────────────────────────────────────────

    def is_write(self, method: str, path: str) -> bool:
        """Return whether a request changes something in Jira."""
        method = method.upper()
        if method in ("GET", "HEAD", "OPTIONS"):
            return False
        return not (method == "POST" and path.split("?", 1)[0] in READ_ONLY_POSTS)

    # Jira's JSON is untyped; callers read the keys they need.
    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        raw: bool = False,
    ) -> Any:
        """Send a request and return its JSON (or the response itself with `raw`)."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        if self.dry_run and self.is_write(method, path):
            return self._plan(method, path, params, body, files)
        try:
            resp = self.session.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                json=body,
                files=files,
                headers=headers,
                timeout=TIMEOUT,
                stream=raw,
            )
        except requests.RequestException as error:
            raise JiraError(f"could not reach {self.base_url}: {error}") from error
        if resp.status_code == 401:
            raise AuthError(
                "Jira rejected the credentials (401). "
                "Run `aj auth login` again with a fresh API token.",
                401,
            )
        if resp.status_code == 404:
            raise NotFoundError(f"not found: {_error_text(resp)}", 404)
        if not resp.ok:
            raise JiraError(
                f"{method} {path} failed with {resp.status_code}: {_error_text(resp)}",
                resp.status_code,
            )
        if raw:
            return resp
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def _plan(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        body: Any,
        files: dict[str, Any] | None,
    ) -> Any:
        names = [str(getattr(f[1], "name", f[0])) for f in (files or {}).values()]
        planned = PlannedRequest(method.upper(), path, params, body, [Path(n).name for n in names])
        self.planned.append(planned)
        if self.on_plan:
            self.on_plan(planned)
        return {"id": DRY_RUN_ID, "key": DRY_RUN_ID, "dryRun": True}

    def get(self, path: str, **params: Any) -> Any:
        """GET a JSON resource."""
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Any = None, **params: Any) -> Any:
        """POST a JSON body and return the JSON response."""
        return self.request("POST", path, params=params, body=body)

    def put(self, path: str, body: Any = None, **params: Any) -> Any:
        """PUT a JSON body and return the JSON response."""
        return self.request("PUT", path, params=params, body=body)

    def delete(self, path: str, **params: Any) -> Any:
        """DELETE a resource."""
        return self.request("DELETE", path, params=params)

    # ── pagination ───────────────────────────────────────────────────────────

    def paged(
        self,
        path: str,
        *,
        limit: int | None = None,
        key: str = "values",
        page_size: int = PAGE_SIZE,
        **params: Any,
    ) -> Iterator[dict]:
        """Yield items from a startAt/maxResults endpoint, up to `limit` (None: all)."""
        start = 0
        seen = 0
        while True:
            size = page_size if limit is None else min(page_size, limit - seen)
            data = self.get(path, startAt=start, maxResults=size, **params)
            page = data if isinstance(data, list) else data.get(key, [])
            for item in page:
                yield item
                seen += 1
                if limit is not None and seen >= limit:
                    return
            start += len(page)
            if not page or (isinstance(data, list) and len(page) < size):
                return
            if isinstance(data, dict):
                if data.get("isLast") is True:
                    return
                if "total" in data and start >= data["total"]:
                    return

    def search(
        self,
        jql: str,
        fields: list[str] | None = None,
        *,
        limit: int | None = None,
        expand: str | None = None,
    ) -> Iterator[dict]:
        """Yield issues matching `jql`, up to `limit` (None: all)."""
        token: str | None = None
        seen = 0
        while True:
            size = SEARCH_PAGE_SIZE if limit is None else min(SEARCH_PAGE_SIZE, limit - seen)
            body: dict[str, Any] = {"jql": jql, "maxResults": size, "fields": fields or ["key"]}
            if expand:
                body["expand"] = expand
            if token:
                body["nextPageToken"] = token
            data = self.post(f"{API}/search/jql", body)
            for issue in data.get("issues", []):
                yield issue
                seen += 1
                if limit is not None and seen >= limit:
                    return
            token = data.get("nextPageToken")
            if not token or data.get("isLast", False):
                return

    def count(self, jql: str) -> int:
        """Return Jira's approximate count of issues matching `jql`."""
        return int(self.post(f"{API}/search/approximate-count", {"jql": jql}).get("count", 0))

    # ── common reads ─────────────────────────────────────────────────────────

    def myself(self) -> dict:
        """Return the calling account's profile."""
        return self.get(f"{API}/myself")

    def issue(self, key: str, fields: list[str] | None = None, expand: str | None = None) -> dict:
        """Return one issue."""
        params: dict[str, Any] = {"expand": expand}
        if fields:
            params["fields"] = ",".join(fields)
        return self.get(f"{API}/issue/{key}", **params)

    def fields(self) -> list[dict]:
        """Return every field on the site."""
        return self.get(f"{API}/field")

    def transitions(self, key: str) -> list[dict]:
        """Return the transitions available on an issue now."""
        return self.get(f"{API}/issue/{key}/transitions").get("transitions", [])

    def link_types(self) -> list[dict]:
        """Return the issue link types."""
        return self.get(f"{API}/issueLinkType").get("issueLinkTypes", [])

    def filter(self, filter_id: str) -> dict:
        """Return a saved filter."""
        return self.get(f"{API}/filter/{filter_id}")

    def download(self, path: str, dest: Path) -> int:
        """Stream a binary resource to `dest`, returning the bytes written."""
        resp = self.request("GET", path, headers={"Accept": "*/*"}, raw=True)
        written = 0
        with resp, dest.open("wb") as handle:
            for chunk in resp.iter_content(chunk_size=65536):
                handle.write(chunk)
                written += len(chunk)
        return written


def _error_text(resp: requests.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:300] or resp.reason
    if not isinstance(data, dict):
        return json.dumps(data)[:300]
    messages = list(data.get("errorMessages") or [])
    messages += [f"{k}: {v}" for k, v in (data.get("errors") or {}).items()]
    if not messages and data.get("message"):
        messages.append(str(data["message"]))
    return "; ".join(messages) or resp.reason
