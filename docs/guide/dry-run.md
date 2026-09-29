# Dry runs and bulk changes

## Dry run

Every command that changes something takes `--dry-run` (`-n`). You can also put it before the
command (`acli-py -n issue delete …`), or set `ACLI_PY_DRY_RUN=1` to make a whole shell session
read-only.

In a dry run, `acli-py` still **reads** from Jira: it finds the issues your JQL selects, resolves
people and fields, and looks up transitions. So what it shows is what would really happen. It
does not send any **write**. Instead it prints each request it would have made:

```console
$ acli-py issue transition DEMO-1 --to "in progress" -m "On it" --dry-run
╭─ DRY RUN POST /rest/api/3/issue/DEMO-1/transitions ─╮
│ {                                                   │
│   "transition": {                                   │
│     "id": "21"                                      │
│   },                                                │
│   "update": {                                       │
│     "comment": [                                    │
│       {                                             │
│         "add": {                                    │
│           "body": "ADF: On it"                      │
│         }                                           │
│       }                                             │
│     ]                                               │
│   }                                                 │
│ }                                                   │
╰─────────────────────────────────────────────────────╯
✔ DEMO-1 would move to In Progress
DRY RUN 1 change planned, nothing was sent to Jira.
```

Rich text (descriptions, comments) is shown as the Markdown you typed, prefixed `ADF:`,
rather than as Jira's verbose document JSON.

The HTTP client enforces the dry run, not each command, so there is no command that "forgets"
it. The test suite also runs every write command with `--dry-run` and checks that the fake Jira
received no writes.

## Choosing issues

Commands that change issues (`edit`, `assign`, `transition`, `delete`, `archive`, `clone`,
`comment add`) accept any mix of:

- keys as arguments: `DEMO-1 DEMO-2` or `DEMO-1,DEMO-2`
- `--jql 'project = DEMO AND labels = legacy'`
- `--filter 10100`, the issues of a saved filter
- `--from-file keys.txt`, with keys separated by commas, spaces or lines (`#` starts a
  comment, and `-` reads standard input)

## Confirmation and errors

Before changing more than one issue, and before any deletion, `acli-py` asks for confirmation.
`--yes` (`-y`) answers for you. Without a terminal (in a script or a pipe), `acli-py` refuses
rather than guess, so scripts must pass `--yes`.

Each issue gets its own ✔ or ✘ line. By default `acli-py` stops at the first failure and reports
how many issues it did not try. `--ignore-errors` keeps going. Either way the exit code is 1
if anything failed, and `--json` prints a per-item result list.
