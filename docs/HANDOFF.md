# Handoff: <Project name> (checkpoint <YYYY-MM-DD HH:MM>)

For the next Claude Code session (ARCHITECT) and for the owner. Read this and `CLAUDE.md` before
acting, then `docs/QUALITY_BAR.md` and `docs/WORK_QUEUE.md`.

> **How to keep this file useful.** Rewrite it at the end of every session; don't append a diary.
> It's the next session's memory, so it holds only what's true *now*. Put dates on facts that
> can go stale. Move finished history to git commit messages, not here.

## Mission and rules
<!-- The goal in one line (with a number if there is one), plus the few rules that override
     everything else. Link to QUALITY_BAR instead of repeating it. -->
- **Goal:** <e.g. "X by <date>", "N users", "$N/month net profit">.
- **Quality:** CRITIC ≥ <9>/10, zero hard fails, judged in the batch (`docs/QUALITY_BAR.md`).
- **Owner:** <who they are, how they like to work (e.g. "wants minimal prompts"), when the
  machine is on or off.>

## Where things live
<!-- Paths, repos, services, and where secrets are (never the secrets themselves). -->
- **Project:** `<path>` (not under a synced folder like OneDrive).
- **Git:** <remote / branch>.
- **Secrets:** in `.env` (gitignored): <names only, e.g. SERVICE_TOKEN>. Never print them.
- **HQ:** `hq/state.db`; dashboard http://127.0.0.1:8787.
- **Daily crew:** `<ProjectName>-DailyCrew` task at <time>; logs in `output/logs/`.

## The crew (`.claude/agents/`)
<!-- One line per role: what it owns and anything unusual about it. -->
- **ARCHITECT:** plans, dispatches, reviews, ships owner-approved work.
- **CRITIC:** the quality gate.
- <ROLE>: <what it owns>.

## Status
<!-- What exists and works today, with numbers. What's half-done and where it stopped. -->
- <status line, with a date>

## Waiting on owner
<!-- Numbered, most important first, each with an estimated time. The owner reads this list. -->
1. <what> (about <N> min): <exact steps or link>.

## Next priorities for ARCHITECT
<!-- Numbered. The first item is what the next session does first. Say why when it isn't obvious. -->
1. <priority>

## Known gotchas
<!-- Things that cost time once and will again: tool quirks, API limits, environment traps. -->
- The Bash tool expands `$_`; use the PowerShell tool for PowerShell one-liners.
- `claude.cmd` mangles quoted prompt arguments; the daily shift pipes its prompt via stdin.
- `pythonw` crashes uvicorn's logging; the HQ task runs `python.exe` in a hidden PowerShell.
- The daily shift commits with `git add -A`, so it also sweeps in other uncommitted work.
- <gotcha>
