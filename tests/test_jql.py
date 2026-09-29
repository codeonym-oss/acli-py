from __future__ import annotations

import pytest

from acli_py.client import JiraClient
from acli_py.jql import Completer, JiraCatalog, StaticCatalog, Value, compile_query, looks_like_jql
from acli_py.jql.lexer import Kind, quote, tokenize
from acli_py.jql.smart import cheatsheet, date_clause
from tests import fake_jira

CATALOG = StaticCatalog(
    field_values={
        "status": [Value("To Do"), Value("In Progress"), Value("Done")],
        "labels": [Value("web"), Value("backend")],
        "priority": [Value("High"), Value("Low")],
        "project": [Value("DEMO", "Demo (DEMO)")],
        "assignee": [Value("acc-bob", "Bob Jensen")],
    },
    issue_values=[Value("DEMO-1", "Login fails"), Value("DEMO-2", "Release notes")],
)
complete = Completer(CATALOG).complete


def texts(query: str, cursor: int | None = None) -> list[str]:
    return [item.text for item in complete(query, cursor).items]


# ── lexer ────────────────────────────────────────────────────────────────────


def test_tokens_keep_positions_and_survive_half_typed_input():
    tokens = tokenize('status != "In Prog')
    assert [t.kind for t in tokens] == [Kind.WORD, Kind.OP, Kind.STRING]
    assert tokens[2].value == "In Prog"
    assert not tokens[2].closed
    assert tokenize("cf[10016] >= -7d")[0].text == "cf[10016]"
    assert [t.text for t in tokenize("a in (b,c)")] == ["a", "in", "(", "b", ",", "c", ")"]
    assert tokenize("!x")[0].text == "!x"
    assert tokenize(r'"a \"b\""')[0].value == 'a "b"'


def test_quote_only_what_needs_it():
    assert quote("DEMO-1") == "DEMO-1"
    assert quote("In Progress") == '"In Progress"'
    assert quote("empty") == '"empty"'  # reserved word
    assert quote('say "hi"') == '"say \\"hi\\""'


# ── JQL completion ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("query", "first"),
    [
        ("status = ", '"To Do" '),
        ("status = In", '"In Progress" '),
        ('status = "In P', '"In Progress" '),
        ("status in (", '"To Do"'),
        ('status in ("To Do", ', '"To Do"'),
        ("status = Done ", "AND "),
        ("status = Done an", "AND "),
        ("status = Done AND ", "project "),
        ("project = DEMO ORDER ", "BY "),
        ("status = Done ORDER BY updated ", "ASC"),
        ("assignee is ", "EMPTY "),
        ("key = DEMO-", "DEMO-1 "),
        ("status ", "= "),
        ("status not ", "in "),
        ("(status = Done ", ") "),
    ],
)
def test_jql_completion_follows_the_grammar(query, first):
    assert texts(query)[0] == first


def test_list_operators_offer_a_list_or_list_functions():
    items = texts("sprint in ")
    assert items[0] == "("
    assert "openSprints() " in items


def test_history_operators_offer_predicates():
    assert "AFTER " in texts("status changed ")
    assert "not " in texts("status was ")
    assert "in " in texts("status was ")


def test_dates_suggest_relative_values():
    assert "-7d " in texts("created > ")


def test_function_arguments_are_skipped():
    assert texts("assignee in membersOf(x) ")[0] == "AND "


def test_completion_replaces_the_word_under_the_cursor():
    text = "status = Don AND project = DEMO"
    found = complete(text, cursor=12)
    assert (found.start, found.end) == (9, 12)
    new, cursor = found.apply(text, found.items[0])
    assert new == "status = Done  AND project = DEMO"
    assert cursor == 14


# ── smart completion ─────────────────────────────────────────────────────────


def test_smart_completion():
    assert texts("")[0] == "project:"
    assert texts("s:pro") == ['s:"In Progress" ']
    assert texts("#w") == ["#web "]
    assert texts("-#")[:2] == ["-#web ", "-#backend "]
    assert texts("@")[:3] == ["@me ", "@none ", "@acc-bob "]
    assert "is:open " in texts("is:")
    assert "sort:-priority" in texts("sort:-")
    assert texts("updated:")[0] == "updated:1d "
    assert texts("p:DEMO s:todo,")[0] == 's:todo,"To Do" '
    assert texts("DEMO-")[:2] == ["DEMO-1 ", "DEMO-2 "]
    assert "is:open " in texts("open")  # flags by their name alone
    assert complete("#we").context == "value of label"


def test_a_word_that_turns_out_to_be_text_falls_back_to_smart():
    assert complete("status report").mode == "smart"


# ── compiling ────────────────────────────────────────────────────────────────


def test_smart_queries_compile_to_jql():
    compiled = compile_query('@me #web s:progress is:open updated:7d "login fails" sort:-priority',
                             resolve=lambda field, value: {"progress": "In Progress"}.get(value, value))  # fmt: skip
    assert compiled.mode == "smart"
    assert compiled.jql == (
        "statusCategory != Done AND updated >= -7d AND assignee = currentUser() AND labels = web"
        ' AND status = "In Progress" AND text ~ "login fails" ORDER BY priority DESC'
    )


def test_negation_keeps_issues_where_the_field_is_empty():
    jql = compile_query("-#legacy -@me -p:ops").jql
    assert "(labels != legacy OR labels is EMPTY)" in jql
    assert "(assignee != currentUser() OR assignee is EMPTY)" in jql
    assert "project != OPS" in jql  # every issue has a project


def test_repeats_and_lists_mean_either():
    assert compile_query("s:todo s:done").where == "status in (todo, done)"
    assert compile_query("a:none,@me").where == "(assignee = currentUser() OR assignee is EMPTY)"
    assert compile_query("sprint:current,42").where == "sprint in (openSprints(), 42)"


def test_keys_text_and_order():
    compiled = compile_query("demo-1 DEMO-2 crash report")
    assert compiled.where == 'key in (DEMO-1, DEMO-2) AND text ~ "crash report"'
    assert compiled.order == "updated DESC"
    assert compile_query("-crash").where == "text !~ crash"
    assert compile_query("sort:type,-due").order == "issuetype ASC, duedate DESC"


def test_jql_passes_through():
    compiled = compile_query("project = DEMO order by key")
    assert (compiled.mode, compiled.where, compiled.order) == ("jql", "project = DEMO", "key")
    assert looks_like_jql("assignee in membersOf(x)")
    assert looks_like_jql("status=Done")
    assert not looks_like_jql("created:<7d #web")
    assert not looks_like_jql('q:"a = b"')


def test_warnings_for_what_cant_be_used():
    compiled = compile_query("colour:red is:shiny s: sort:")
    assert compiled.warnings == [
        "unknown filter colour: (searched as text)",
        "is:shiny: unknown (try "
        + ", ".join(__import__("acli_py.jql.smart", fromlist=["FLAGS"]).FLAGS)
        + ")",
        'status: needs a value, e.g. s:"In Progress"',
        "sort: give at least one field",
    ]
    assert compiled.where == 'text ~ "colour:red"'


@pytest.mark.parametrize(
    ("field", "value", "jql"),
    [
        ("updated", "7d", "updated >= -7d"),
        ("updated", ">30d", "updated <= -30d"),
        ("created", "2w", "created >= -2w"),
        ("duedate", "3d", "duedate <= 3d"),
        ("duedate", ">1w", "duedate > 1w"),
        ("duedate", "today", "duedate <= endOfDay()"),
        ("created", "week", "created >= startOfWeek()"),
        ("created", "none", "created is EMPTY"),
        ("created", "2026-09-01", 'created >= "2026-09-01" AND created < "2026-09-02"'),
        ("created", "2026-09-01..2026-09-30", 'created >= "2026-09-01" AND created < "2026-10-01"'),
        ("created", "..2026-09-30 10:00", 'created <= "2026-09-30 10:00"'),
        ("created", "<2026-09-01", 'created < "2026-09-01"'),
    ],
)
def test_dates(field, value, jql):
    assert date_clause(field, value) == jql


def test_bad_dates_say_what_works():
    with pytest.raises(ValueError, match="try 7d"):
        compile_query("updated:soon")


def test_cheatsheet_lists_every_filter():
    names = {row[0] for row in cheatsheet()}
    assert {"@NAME", "is:", "sort:", "-TERM"} <= names


# ── the live catalog ─────────────────────────────────────────────────────────


def test_jira_catalog_reads_the_site_and_caches(site, fake):
    _, url = fake
    client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN)
    catalog = JiraCatalog(client)
    completer = Completer(catalog)
    assert "cf[10016] " in [i.text for i in completer.complete("status = Done AND cf").items]
    assert [i.text for i in completer.complete("status = in").items] == ['"In Progress" ']
    assert [v.value for v in catalog.issues("DEMO-1")] == ["DEMO-1"]
    assert catalog.values("assignee", "bob")[0].display == "Bob Jensen"
    calls = len(site.log)
    catalog.fields()
    catalog.values("status", "in")
    assert len(site.log) == calls  # cached
    catalog.clear()
    catalog.fields()
    assert len(site.log) == calls + 1


def test_jira_catalog_never_raises(jira):
    client = JiraClient("http://127.0.0.1:9", "x", "y", retries=0)
    catalog = JiraCatalog(client)
    assert catalog.fields()  # the built-in fields
    assert catalog.values("status", "") == []
    assert catalog.issues("DEMO") == []
    assert next(f.name for f in catalog.functions()) == "currentUser()"
