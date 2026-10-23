# Telegram Bot Development Skill

[![Download Telegram Bot Development Skill](https://img.shields.io/badge/Download-telegram--bot--development.skill-blue?style=for-the-badge)](https://github.com/nyxandro/telegram-bot-development-skill/raw/main/dist/telegram-bot-development.skill)

A Telegram bot development skill for Claude Code and OpenCode: build, review and debug Telegram
bots and Mini Apps against the current Bot API. The Bot API ships a release about every month,
and a release can replace what the previous one added. An agent writing from memory calls
parameters that no longer exist, works around features the API now has natively, and quotes
limits and fees from a year ago. This skill makes the agent check the live official
documentation and the library installed in the project before it writes, reviews or recommends
any Bot API call.

It is neutral about language and framework: grammY, Telegraf, aiogram, python-telegram-bot,
GramIO, Go, Rust, PHP and .NET libraries, or raw HTTPS. The docs decide what exists; the
installed library decides what the project can call.

## Quick install

In Claude Code, run:

```text
/plugin install telegram-bot-development --marketplace nyxandro/skills
```

The skill is listed in [nyxandro/skills](https://github.com/nyxandro/skills), the catalog of my
skills. Older Claude Code, updates, and other agents: see [Install](#install).

## What the agent does

1. Finds the current Bot API version and reads every change since the version the project's
   library declares.
2. Reads the official page of every method and type it touches, and the history of any name it
   is unsure is still alive.
3. Checks that the installed library accepts that parameter on that method, not merely that the
   name occurs somewhere in its code. A library that still accepts a replaced parameter, kept as
   deprecated, is not a reason to use it.
4. Before saying "Telegram can't do that", reads the features page and searches the docs.
5. Says what it checked: the Bot API version and date, and whether the installed library
   supports what it used.

Beyond freshness, eleven references are read only when the task needs them: receiving updates
(polling, webhooks, at-least-once delivery, duplicates), conversation design and keyboards,
security and privacy, limits and broadcasts, errors and edge cases, product features and the
BotFather settings code cannot change, Stars payments, Mini Apps, AI bots (streaming drafts and
their rate limits, rich messages, bot-to-bot, guest mode), and a review checklist before release.
The developer terms are read clause by clause, including the fee on Stars purchases in bots that
enable topics in private chats.

## Tools

Two scripts, Python 3.8 or newer, standard library only:

```text
scripts/tgdocs.py                  the official docs in their Markdown form: latest version,
                                   changes since a version, a method or type page, search,
                                   the history of a name, any guide (--toc, --section),
                                   the developer terms (terms --section 6.2.6)
scripts/find_method_support.py     the Telegram libraries installed in a project and whether
                                   each knows a method, a type or METHOD.PARAMETER, with the lines
```

Pages are cached for six hours in `~/.cache/telegram-bot-docs`. Without Python, the skill gives
the agent the same official pages as plain URLs.

## Install

**Claude Code, as a plugin.** The plugin comes from [nyxandro/skills](https://github.com/nyxandro/skills),
the catalog of my skills. Run in a Claude Code session:

```text
/plugin install telegram-bot-development --marketplace nyxandro/skills
```

This adds the catalog and installs the plugin from it, on Claude Code 2.1.275 or later. On an
older version, add the catalog first:

```text
/plugin marketplace add nyxandro/skills
/plugin install telegram-bot-development@nyxandro
```

No version is pinned, so every commit to this repository is a new version. To take it, run
`claude plugin marketplace update nyxandro` and then
`claude plugin update telegram-bot-development@nyxandro` in your shell, or turn on auto-update
for the catalog under `/plugin` → Marketplaces.

**Any agent, as a skill folder.** Download `dist/telegram-bot-development.skill` (the badge
above) and unpack it into the skills folder of your agent, or clone this repository and link the
`telegram-bot-development/` folder there. No build step. Install it one way or the other, not
both: with both, Claude Code loads the skill twice.

The scripts need Python 3.8 or newer and access to core.telegram.org and telegram.org. On
Windows the interpreter is usually `py -3` or `python`. On macOS with Python from python.org,
run `Install Certificates.command` once, or HTTPS requests fail. Tested on Linux and Windows.

## Tests

```bash
uv run --with pytest --with hypothesis python -m pytest test
```

Offline: the docs and the libraries are replaced by small fake pages and packages. pytest and
Hypothesis are needed only for the tests, not by the skill.

`telegram-bot-development/evals/` holds test tasks for the agent, their assertions and the
results of past runs, with the fixtures described in its README. It is left out of the archive.

## Repository layout

```text
telegram-bot-development/             the skill itself
  SKILL.md                            the workflow: the live API and the installed library first
  references/                         eleven references, read only when the task needs them
  scripts/tgdocs.py                   the official docs, live
  scripts/find_method_support.py      what the project's installed library knows
  evals/                              test tasks for the agent and their results (not in the archive)
test/                                 offline tests of both scripts
dist/telegram-bot-development.skill   downloadable archive of the skill folder
```

## License

MIT.
