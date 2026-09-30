from __future__ import annotations

from typing import Any

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.clone_issue.command import CloneIssue
from acli_py.application.ports import Destination, IssueEditor, IssueLinks, IssueReader
from acli_py.domain.copies import COPIED, copy_of

# The link type that says one issue is a copy of another ('DEMO-9 clones DEMO-1').
CLONERS = "Cloners"


@command_handler
def clone_issue(
    request: CloneIssue,
    editor: IssueEditor,
    reader: IssueReader,
    links: IssueLinks,
    there: Destination,
) -> Changed:
    """Copy the issue and link the copy; `Changed` names the copy (undoing it deletes it)."""
    key = request.key.strip().upper()
    original = editor.values(key, COPIED)
    fields = copy_of(
        original, project=request.project, prefix=request.prefix, same_site=not there.elsewhere
    )
    copy = there.create(fields, {})
    if request.link and there.elsewhere:
        there.web_link(copy, reader.browse_url(key), f"Cloned from {key}")
    elif request.link and (cloners := links.link_type(CLONERS)):
        links.link(cloners, copy, key)  # the outward ("from") issue is the copy
    after: dict[str, Any] = {"created": copy, "clone_of": key}
    if there.elsewhere:
        after["site"] = there.url
    return Changed(copy, after=after)
