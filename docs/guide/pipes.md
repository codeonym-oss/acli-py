# Pipes

`acli-py` commands chain with shell pipes: one command finds issues, and the next acts on
them.

```sh
acli-py issue search '@me is:open #web' --output keys | acli-py issue transition - --to Done
acli-py issue search 'is:overdue' --output jsonl | acli-py issue edit - --priority High
```

## Reading issues from stdin

Every command that takes issue keys accepts `-` in their place. It reads the keys from
standard input, in any of these forms:

- **Keys**, one per line or separated by commas or spaces. `#` starts a comment.
- **JSON lines** (`--output jsonl`). Each line's `key` is used, or its `id` if it has no `key`.
- **A JSON array** (`--json`), read the same way.

`-` can be combined with keys typed on the command line, `--jql` and `--filter`.
`--from-file -` reads from stdin the same way.

When the command upstream finds nothing, the pipe is empty and nothing is changed. The command
says so and exits 0.

## Printing for the next command

Every command that lists things takes `--output`:

| `--output` | Prints |
|---|---|
| `table` | The default: a table for people. |
| `json` | One JSON array. Same as `--json`. |
| `csv` | CSV with a header row. Same as `--csv`. |
| `keys` | One key per line. For rows without one: the id, account id or name. |
| `jsonl` | One JSON object per line. |

Results go to stdout. Messages, progress and dry-run plans go to stderr, so they never end up
in the next command's input.

## Asking mid-pipe

A command that reads its issues from stdin can't read your answer from stdin as well.

- **On a terminal:** it asks on the terminal itself (`/dev/tty`, or the console on Windows).
  The preview and the question show as usual, and you answer them there.
- **With no terminal at all** (cron, CI, a detached job): it refuses, and exits 2 without
  changing anything, unless you pass `--yes`.

```console
$ acli-py issue search 'p:DEMO s:review' --output keys | acli-py issue transition - --to Done
Issue   Summary                Now     After
DEMO-1  Login fails on Safari  Review  →  Done
DEMO-3  Speed up search        Review  →  Done
Move 2 issues (DEMO-1, DEMO-3) to Done? [y/N]: y
```

`--dry-run` also works mid-pipe: it shows the requests without asking.

## Stopping early

A reader that stops early, like `| head -3`, ends the command quietly. It prints no traceback
and no "Broken pipe" error, and exits 141, the way shell tools stopped by `SIGPIPE` do.

## Recipes

Move everything you have in review to Done:

```sh
acli-py issue search '@me s:review' --output keys | acli-py issue transition - --to Done
```

Raise the priority of overdue issues, checking the plan first:

```sh
acli-py issue search 'is:overdue' --output jsonl | acli-py issue edit - --priority High --dry-run
```

Hand your open issues in one project to someone else:

```sh
acli-py issue search '@me is:open p:DEMO' --output keys | acli-py issue assign - --to bob@example.com
```

Put this sprint's leftovers into the next sprint:

```sh
acli-py sprint issues 7 --output keys | acli-py sprint add 8 -
```

Keep a list of issues, and act on it later:

```sh
acli-py issue search 'label = legacy' --output keys > legacy.txt
acli-py issue edit --from-file legacy.txt --remove-label legacy
```

Filter the JSON with `jq` before acting on it:

```sh
acli-py issue search 'p:DEMO' --output jsonl \
  | jq -c 'select(.fields.priority.name == "Lowest")' \
  | acli-py issue transition - --to "Won't Do" --continue-on-error
```

Combine piped issues with keys typed on the command line:

```sh
acli-py issue search '#web is:open' --output keys | acli-py issue assign - DEMO-42 --to @me
```

Log the same time on every issue a search finds, or link each one to an epic's blocker:

```sh
acli-py issue search 'sprint:open assignee:me' --output keys | acli-py issue worklog add - -t 15m -y
acli-py issue link add --jql 'labels = login' "is blocked by" DEMO-7
```

`issue link list KEY --output keys` prints the linked issues, ready for the next command.

In scripts, where there is no terminal to ask on, pass `--yes`:

```sh
acli-py issue search 'status = Resolved AND updated < -30d' --output keys \
  | acli-py issue transition - --to Closed --yes
```

`issue comment add` can take its issues from stdin, or its body (`--body -`), but not both.
Standard input can only be read once.
