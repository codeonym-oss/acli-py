# Getting started

## Install

`aj` needs Python 3.11 or newer, on Linux, macOS or Windows. Install it in its own environment
with [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/):

```sh
uv tool install git+https://github.com/codeonym-oss/acli-py
aj --version
```

This installs two identical commands: `aj`, and `acli-py` for when `aj` is taken.

## Log in

Create an API token at <https://id.atlassian.com/manage-profile/security/api-tokens>, then:

```sh
aj auth login            # asks for the site, your email and the token (typed hidden)
```

`aj` checks the token with Jira before saving anything. It stores the token in the system
keyring, or in an owner-only `credentials.json` when there is no keyring (headless servers,
WSL, containers). The config file never holds tokens.

Log in again with another site or email to add an account. `aj auth status` lists them,
`aj auth switch` changes the active one, and `aj --account EMAIL@SITE …` uses another one for
a single command.

For scripts, read the token from standard input:

```sh
echo "$TOKEN" | aj auth login -s team.atlassian.net -e me@example.com --token-stdin
```

In CI, skip the login entirely and set `ACLI_PY_SITE`, `ACLI_PY_EMAIL` and
`ACLI_PY_API_TOKEN`.

## Set your defaults

```sh
aj config set project DEMO        # used whenever -p is left out
aj config set issue-type Story    # used by `aj issue create` when -t is left out
aj config set board 12            # used by sprint commands when --board is left out
aj config show
```

## Everyday commands

```sh
aj issue search -a @me --open                 # what's on my plate
aj issue view DEMO-12                         # details, description, links, comments
aj issue create -s "Fix the flaky test" -t Bug -a @me
aj issue transition DEMO-12 --to Done -m "Fixed in #431"
aj issue comment add DEMO-12 -b "Deployed to **staging**"
aj issue worklog add DEMO-12 "1h 30m" -m "Pairing"
aj sprint issues 42 --csv > sprint.csv
```

People can be named as `@me`, by email, by part of their name, or by account id. When a
name matches several people, `aj` lists them and asks you to be more specific.
