# Changelog

The current version is `metadata.version` in `telegram-bot-development/SKILL.md`. Every version is
tagged `vX.Y.Z` in git and published as a GitHub release with its own `.skill` archive. Versions
are numbered MAJOR.MINOR.PATCH.

- **PATCH** (1.0.1) is a fix or clearer wording. The skill behaves the same.
- **MINOR** (1.1.0) is a new or changed rule, reference or script feature.
- **MAJOR** (2.0.0) changes how the skill works with the user or what the scripts expect.

## [1.0.0] - 2026-11-06

The first numbered version. The skill itself is unchanged since `cfab0b7`. This release adds the
version number to `SKILL.md`.

## Before 1.0.0

- **2026-10-24.** The skill installs as a Claude Code plugin with one `/plugin` command from the
  [nyxandro/skills](https://github.com/nyxandro/skills) catalog (`c9801a8`, `4953eef`).
- **2026-10-23.** First version. The agent checks the live Bot API docs and the installed library
  before any call, with the `tgdocs.py` and `find_method_support.py` scripts and eleven references
  (`b7c2700`).
