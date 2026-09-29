# Getting started

## Install

`acli-py` needs Python 3.11 or newer, on Linux, macOS or Windows. Install it in its own environment
with [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/):

```sh
uv tool install git+https://github.com/codeonym-oss/acli-py
acli-py --version
```

This installs the `acli-py` command.

## Log in

Create an API token at <https://id.atlassian.com/manage-profile/security/api-tokens>, then:

```sh
acli-py auth login            # asks for the site, your email and the token (typed hidden)
```

`acli-py` checks the token with Jira before saving anything. It stores the token in the system
keyring, or in an owner-only `credentials.json` when there is no keyring (headless servers,
WSL, containers). The config file never holds tokens.

Log in again with another site or email to add an account. `acli-py auth status` lists them,
`acli-py auth switch` changes the active one, and `acli-py --account EMAIL@SITE …` uses another one for
a single command.

For scripts, read the token from standard input:

```sh
echo "$TOKEN" | acli-py auth login -s team.atlassian.net -e me@example.com --token-stdin
```

In CI, skip the login entirely and set `ACLI_PY_SITE`, `ACLI_PY_EMAIL` and
`ACLI_PY_API_TOKEN`.

## Set your defaults

```sh
acli-py config set project DEMO        # used whenever -p is left out
acli-py config set issue-type Story    # used by `acli-py issue create` when -t is left out
acli-py config set board 12            # used by sprint commands when --board is left out
acli-py config show
```

## Everyday commands

```sh
acli-py issue search -a @me --open                 # what's on my plate
acli-py issue view DEMO-12                         # details, description, links, comments
acli-py issue create -s "Fix the flaky test" -t Bug -a @me
acli-py issue transition DEMO-12 --to Done -m "Fixed in #431"
acli-py issue comment add DEMO-12 -b "Deployed to **staging**"
acli-py issue worklog add DEMO-12 "1h 30m" -m "Pairing"
acli-py sprint issues 42 --csv > sprint.csv
```

People can be named as `@me`, by email, by part of their name, or by account id. When a
name matches several people, `acli-py` lists them and asks you to be more specific.

## Next

Browse and change issues in the full-screen UI with `acli-py tui`, or run commands with completion
in `acli-py shell`. Both take smart queries such as `@me is:open #web`. See
[Interactive](interactive.md).
