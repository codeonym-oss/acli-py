# Changelog

## [0.3.0](https://github.com/codeonym-oss/acli-py/compare/v0.2.0...v0.3.0) (2026-10-02)


### ⚠ BREAKING CHANGES

* --json on `user search/view`, `meta …` and `issue transitions` prints the views' JSON (people as accountId, name, email…; a transition's `to` is its status name) instead of Jira's raw responses.
* --json on project, board, sprint, filter, field and dashboard commands prints the views' JSON (camelCase, people as {accountId, name, email}) instead of Jira's raw responses. Every write now asks first: project update/restore, sprint update/start/add/remove, filter update/star/columns and field update/restore take --yes in scripts, and a declined change exits 2 instead of 1.
* the parts' --json output uses the views' shapes; comment edit and comment add --edit-last now ask (pass --yes); worklog add takes --time for many issues (KEY TIME still works).
* audit.jsonl lines now hold "changes" (key, before, after per issue) and "failed" instead of top-level "before"/"after", and a declined confirmation exits 2 instead of 1.
* `issue transition` asks before moving even a single issue, and refuses without --yes when there is no terminal to ask on (scripts must pass --yes).
* `acli-py issue view --json` prints the issue view (key, summary, status {name, category}, assignee {accountId, name, email}, links, comments {total, items}, extra fields under "fields") instead of Jira's raw JSON.
* the `aj` command is no longer installed; use `acli-py`.

### Features

* chain commands with pipes ([#12](https://github.com/codeonym-oss/acli-py/issues/12)) ([#29](https://github.com/codeonym-oss/acli-py/issues/29)) ([dcb2ccc](https://github.com/codeonym-oss/acli-py/commit/dcb2cccb8e0700e3c19040ef0a322b16fff89c46))
* comments, links, attachments and worklogs through commands and queries ([#15](https://github.com/codeonym-oss/acli-py/issues/15)) ([#32](https://github.com/codeonym-oss/acli-py/issues/32)) ([8470550](https://github.com/codeonym-oss/acli-py/commit/8470550edbe46059b47f425b0418a3b9d189bfdb))
* create, clone, delete and archive issues through commands ([#14](https://github.com/codeonym-oss/acli-py/issues/14)) ([#31](https://github.com/codeonym-oss/acli-py/issues/31)) ([a81b32c](https://github.com/codeonym-oss/acli-py/commit/a81b32c977a4c2070935a6a7e337877331295259))
* edit, assign and watch issues through commands, asking first ([#13](https://github.com/codeonym-oss/acli-py/issues/13)) ([#30](https://github.com/codeonym-oss/acli-py/issues/30)) ([046afab](https://github.com/codeonym-oss/acli-py/commit/046afab771dbbf90f74074dc2cc7e7cd0e5eba3f))
* issue export, standup, sprint report, git names and aliases ([#21](https://github.com/codeonym-oss/acli-py/issues/21)) ([#36](https://github.com/codeonym-oss/acli-py/issues/36)) ([30d7d04](https://github.com/codeonym-oss/acli-py/commit/30d7d04f89cec377773df6137098c71ebe3884a2)), closes [#20](https://github.com/codeonym-oss/acli-py/issues/20)
* log, undo and issue import through one plan-then-bulk path ([#19](https://github.com/codeonym-oss/acli-py/issues/19)) ([#35](https://github.com/codeonym-oss/acli-py/issues/35)) ([9d0eb6a](https://github.com/codeonym-oss/acli-py/commit/9d0eb6a699afc6681c4a4b87c6f4d864e8866b26))
* move issue reads to queries with views ([#16](https://github.com/codeonym-oss/acli-py/issues/16)) ([#33](https://github.com/codeonym-oss/acli-py/issues/33)) ([3bf4ecf](https://github.com/codeonym-oss/acli-py/commit/3bf4ecfb7650891e8323d5e423b3d915cfe40a56))
* move issues through the TransitionIssue command, asking first ([#10](https://github.com/codeonym-oss/acli-py/issues/10)) ([#27](https://github.com/codeonym-oss/acli-py/issues/27)) ([29dc5db](https://github.com/codeonym-oss/acli-py/commit/29dc5db0f4fb296b7adb39810103c29d4516d937))
* projects, boards, sprints, filters, fields and dashboards through the bus ([#17](https://github.com/codeonym-oss/acli-py/issues/17)) ([#34](https://github.com/codeonym-oss/acli-py/issues/34)) ([4b09b89](https://github.com/codeonym-oss/acli-py/commit/4b09b8989f0aed0f1e459cccd61c1367022ec0a4))
* run commands over many issues through the bulk engine ([#11](https://github.com/codeonym-oss/acli-py/issues/11)) ([#28](https://github.com/codeonym-oss/acli-py/issues/28)) ([2230cd7](https://github.com/codeonym-oss/acli-py/commit/2230cd7115143cb36b9b56b68bd631e5cbc54d2f))
* show issues through the GetIssue query and IssueView ([#9](https://github.com/codeonym-oss/acli-py/issues/9)) ([#26](https://github.com/codeonym-oss/acli-py/issues/26)) ([7c05d4c](https://github.com/codeonym-oss/acli-py/commit/7c05d4c05d2cb7448f4b0220f55b5bacbebf467e))


### Bug Fixes

* harden undo, import and export ([#19](https://github.com/codeonym-oss/acli-py/issues/19)) ([#38](https://github.com/codeonym-oss/acli-py/issues/38)) ([ea61c7b](https://github.com/codeonym-oss/acli-py/commit/ea61c7b568059ab971aae1ecaa595d2d2e3881d2))


### Refactoring

* contract the layers, no import-linter exceptions left ([#18](https://github.com/codeonym-oss/acli-py/issues/18)) ([#37](https://github.com/codeonym-oss/acli-py/issues/37)) ([a699c8e](https://github.com/codeonym-oss/acli-py/commit/a699c8eee2f310130a954f427bdd560c3c997aad))
* rename the command to acli-py ([#7](https://github.com/codeonym-oss/acli-py/issues/7)) ([#23](https://github.com/codeonym-oss/acli-py/issues/23)) ([866f847](https://github.com/codeonym-oss/acli-py/commit/866f84775fdd7c60cdc2ce9f7ca36317fad69019))

## [0.2.0](https://github.com/codeonym-oss/acli-py/compare/v0.1.0...v0.2.0) (2026-09-29)


### Features

* aj tui, aj shell and smart queries, with every acli flag covered ([#3](https://github.com/codeonym-oss/acli-py/issues/3)) ([574dcc7](https://github.com/codeonym-oss/acli-py/commit/574dcc79dd25185d844996e17684eef44c71f66d)), closes [#2](https://github.com/codeonym-oss/acli-py/issues/2)


### Documentation

* point from getting started to the TUI and the shell ([#6](https://github.com/codeonym-oss/acli-py/issues/6)) ([328e214](https://github.com/codeonym-oss/acli-py/commit/328e214b79e15802ef75e677d48d28a1f0aaeabf)), closes [#5](https://github.com/codeonym-oss/acli-py/issues/5)

## 0.1.0 (2026-09-29)


### Features

* the aj command line for Jira Cloud ([9eb5f2d](https://github.com/codeonym-oss/acli-py/commit/9eb5f2d0ba05fe2744cfbf79fbaa2dcbfd0a0e4f))


### Documentation

* README, guides and a command reference generated from the CLI ([59bb4ff](https://github.com/codeonym-oss/acli-py/commit/59bb4ffc8fdf47e2a12dbda2edfbd12b311ea0b0))


### Build

* set up the project with the codeonym-oss tooling ([831a084](https://github.com/codeonym-oss/acli-py/commit/831a0840e9628ee51d3f0a668d3372724399fd3a))
