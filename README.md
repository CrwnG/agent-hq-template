# Agent HQ template

A starter kit for running a project with a **crew of Claude Code agents**. An ARCHITECT lead
plans and dispatches the work, a CRITIC quality gate holds the bar, and you add specialist
roles. The crew reports to a local **HQ**: a SQLite state file and a pixel-art dashboard where
you watch the robots walk, sit and work, read the event feed, and **approve or reject** what
they want to ship. A scheduled **daily shift** runs the crew unattended on your Claude
subscription, and it has been hardened by real failures.

```
.claude/agents/      the crew: architect, critic, researcher + builder (examples), _TEMPLATE.md
.claude/commands/    daily-crew.md: the unattended shift's prompt
hq/                  state.db (agents, events, approvals, optional ledger) + the report/query CLIs
dashboard/           FastAPI app on :8787: station view, roster, events, approval queue, plugins
scripts/             daily_crew.ps1, install_schedule.ps1, claim_day.ps1, crew.config.ps1
docs/                HANDOFF.md, QUALITY_BAR.md, WORK_QUEUE.md (templates to fill in)
tests/               pytest suite (hq, dashboard, ledger, script hardening)
```

Windows-first (the scheduler scripts are PowerShell + Task Scheduler). The Python (HQ,
dashboard, tests) is cross-platform. On macOS or Linux, use `.venv/bin/python` and schedule
`claude -p` with cron or launchd yourself.

## 10-minute setup

Prerequisites: Python 3.11+, Git, and [Claude Code](https://docs.claude.com/en/docs/claude-code)
logged in to your subscription (`claude` works in a terminal).

1. **Create your project from this template** and clone it somewhere that is *not* a synced
   folder (OneDrive or Dropbox locks SQLite and `.venv` files):
   ```powershell
   gh repo create my-project --private --template CrwnG/agent-hq-template --clone
   cd my-project
   ```
2. **Virtual env + dependencies:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   .venv\Scripts\python.exe -m pytest -q          # should be all green
   ```
3. **Settings:** `copy .env.example .env`, then set `HQ_PROJECT_NAME` (and `HQ_GOAL_CENTS` if
   you track money). Put your project's secrets in `.env` too; it's gitignored.
4. **Create the HQ database** (tables + the crew from `hq/crew.json`):
   ```powershell
   .venv\Scripts\python.exe -m hq.report init
   ```
5. **Start the dashboard:** double-click `START_HQ.cmd`, or run
   ```powershell
   .venv\Scripts\python.exe -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8787
   ```
   Open http://127.0.0.1:8787. Try `python -m hq.report heartbeat builder working "Hello"` and
   watch BUILDER get up and walk.
6. **Add an agent:** copy `.claude/agents/_TEMPLATE.md` to `.claude/agents/<role>.md`, fill it
   in (the file explains each field), and register it on the station:
   ```powershell
   .venv\Scripts\python.exe -m hq.report agent add analyst ANALYST "Numbers and trends" --room analytics
   ```
   Delete `researcher.md` / `builder.md` if you don't want them (and their `hq/crew.json` lines).
7. **Make it yours:** edit `CLAUDE.md` (the project, the owner, the non-negotiables),
   `docs/QUALITY_BAR.md` (your gate table, hard-fail list and rubric anchors), the `<...>`
   steps in `.claude/commands/daily-crew.md`, and `docs/HANDOFF.md`.
8. **Schedule the daily shift:** set `$ProjectName` and `$RunTime` in
   `scripts/crew.config.ps1`, then:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install_schedule.ps1
   powershell -ExecutionPolicy Bypass -File scripts\daily_crew.ps1 -DryRun   # what would it do now?
   ```
   This registers `<ProjectName>-DailyCrew` (the shift) and `<ProjectName>-HQ` (the dashboard
   at logon). To run a shift right now: `scripts\daily_crew.ps1 -Force`. To remove both tasks:
   `scripts\uninstall_schedule.ps1`.

## How a day works

1. At `$RunTime` (or at the next logon if the machine was off; see below), Task Scheduler runs
   `scripts/daily_crew.ps1`. It checks whether today's shift is due, then pipes
   `.claude/commands/daily-crew.md` into `claude -p` with a tight tool allowlist.
2. ARCHITECT heartbeats `working` and reads HANDOFF, QUALITY_BAR and WORK_QUEUE. Then it
   checks what you decided since the last shift: approved, rejected (with your notes), and
   still pending.
3. **Research** (when it's due): @researcher writes a sourced brief to `research/`.
4. **Build:** @builder works the **Open** items in `docs/WORK_QUEUE.md`, top to bottom, up to
   the daily cap.
5. **Quality gate:** @critic judges the day's work *as a batch*. A pass (score ≥ the bar, zero
   hard fails) goes into your approval queue (`hq.report submit`). A fail goes back to the
   builder once with concrete fixes; if it fails twice, it's parked under **Held**.
6. **Ship:** ARCHITECT acts only on items *you* approved, then marks them `shipped`.
7. **Money** (optional): only real transactions it can verify go into the ledger.
8. **Report:** `output/reports/<date>.md`, with what was done and **your checklist for today**
   (items to approve, things only you can do, each with a time estimate). HANDOFF and
   WORK_QUEUE are updated for the next session.
9. **Commit** (`git add -A`), heartbeat `idle`, and the log gets its `=== Finished ...` marker.

Working interactively instead? Run `scripts\claim_day.ps1` first so the scheduled shift doesn't
start a second ARCHITECT on top of you (`-Release` undoes it).

## How the owner approves

- The dashboard's **APPROVAL QUEUE** shows every item CRITIC passed, with its thumbnail (any
  image under `output/`), score, summary and link. The top bar shows **WAITING ON YOU**.
- **APPROVE**: optionally edit the title first (EDIT) and leave a note. The crew reads your note
  before it ships.
- **REJECT**: say why in the note. ARCHITECT turns it into a WORK_QUEUE fix or drops the item.
- Nothing leaves the machine without an approval: `hq.report shipped` refuses any item that
  isn't `approved`. The crew lists your decisions with
  `python -m hq.report approvals --status approved|rejected`.
- Money: the **$ MONEY** panel (ledger plugin) shows the month's P&L and lets you record real
  transactions by hand. Turn it off with `HQ_PLUGINS=` in `.env`.
- The dashboard is local-only: it refuses non-local Host headers and cross-site writes, so a web
  page you visit can't approve anything on your behalf.

## HQ reference

```powershell
python -m hq.report init
python -m hq.report heartbeat <agent> working|idle|blocked|offline ["task"]
python -m hq.report event <agent> "message" [--level info|success|warn|error]
python -m hq.report agent add <id> [NAME] ["role"] [--room <room>]   |   agent list
python -m hq.report submit "title" --by critic --score 9.2 [--kind page] [--summary ...] [--file output/x.png] [--link URL]
python -m hq.report approvals [--status pending|approved|rejected|shipped]
python -m hq.report shipped <id> [--note "where"]
python -m hq.report ledger sale|refund|fee|cost|investment|payout <signed cents> --platform p --ref unique-id
python -m hq.query "SELECT ... "            # read-only SQL (SELECT/WITH/PRAGMA; opened mode=ro)
```

Station rooms with their own props: `bridge`, `qa_lab`, `observatory`, `workshop`,
`analytics`, `security`, `comms`, `broadcast`, `vault`. Any other room name gets a generic room.
An agent that stops heartbeating for 10 minutes while `working` is shown as idle.

Settings (`.env`, only `HQ_*` keys are read): `HQ_PROJECT_NAME`, `HQ_PLUGINS` (default
`ledger`), `HQ_PASS_SCORE` (default 9), `HQ_GOAL_CENTS` (default 0 = no goal bar).
Dashboard plugins live in `dashboard/plugins/`; see its `__init__.py` for the contract.

## Lessons baked in

Every item below cost a failed run or a bad morning before it was fixed.

- **The prompt goes in on stdin.** Passed as an argument through `claude.cmd`, cmd.exe mangles
  its quotes, and the shift runs a garbled prompt.
- **`--permission-mode dontAsk` with an allowlist.** Nobody is there to answer a permission
  prompt, so anything off the list is refused instead of hanging the run. Add tools in
  `crew.config.ps1` (`$ExtraAllowedTools`), deliberately.
- **`ANTHROPIC_API_KEY` is removed before the run.** If it's set, `claude -p` bills the API
  instead of using your subscription.
- **Secrets are masked in the logs.** Every value in `.env` plus common key and token shapes
  (`sk-ant-...`, `ghp_...`, bearer tokens) is redacted, so a log you paste into a chat can't
  leak a key.
- **A wake lock for the whole shift.** Windows puts the machine back to sleep after its idle
  timeout, even mid-run, and that kills the shift. The lock is released in a `finally`.
- **A daily trigger plus a logon catch-up trigger (+10 min).** A laptop that's off or asleep at
  run time still gets its shift, a few minutes after you log on.
- **A `=== Finished ... exit code 0 ===` marker.** Re-triggers (logon, a second daily trigger)
  see that today is done and exit straight away.
- **A `=== Claimed by interactive session` marker** (`claim_day.ps1`). The scheduled run won't
  start a second ARCHITECT while you're working interactively, and a claimed day counts as done.
- **Missed-day catch-up.** If the last finished shift wasn't yesterday (the machine was off all
  day, or yesterday's shift failed), the next logon runs the shift at once, whatever the time.
- **The interrupted-shift resume note.** If today's shift started but never finished (a shutdown
  or sleep killed it), the re-run is told to check HQ events and git log and finish the job
  rather than redo it.
- **Log markers tolerate the UTF-8 BOM** that Windows PowerShell writes at the start of a file.
  Otherwise a marker on the first line is invisible.
- **UTF-8 stdin.** Windows PowerShell pipes text to native programs as ASCII by default, turning
  every non-ASCII character in the prompt into `?`.
- **The dashboard task runs `python.exe` in a hidden PowerShell,** not `pythonw`: pythonw has no
  stdout, and that crashes uvicorn's logging.
- **The daily trigger is stored in local time with no UTC offset,** so it stays at `$RunTime`
  across daylight-saving changes instead of drifting an hour.
- **Run time and project name are configurable** in one place (`scripts/crew.config.ps1`), and
  `daily_crew.ps1 -DryRun` tells you what the shift would do right now.
- **The quality bar is a gate, not a vibe.** Hard fails cap the score at 4. "No defects" is a
  7-8; a 9 must beat our recent work. Work is judged in its batch (a re-skin is a fail). If
  CRITIC is unsure, it's a fail. The bar is never lowered for a deadline, and `hq.report submit`
  refuses a score under `HQ_PASS_SCORE`.
- **Only owner-approved work ships,** and the crew never spends money or creates accounts. The
  ledger holds real transactions only, deduplicated by reference.
- **The shift commits with `git add -A`,** so commit or stash your own work before it runs.
- **Keep the project out of OneDrive and other synced folders.** Sync clients lock SQLite and
  `.venv` files mid-run.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

This covers the HQ state and CLIs, the dashboard API and its security guards, the ledger, and
the daily-shift hardening. On Windows it also runs the shift's go/skip decision table through
PowerShell with `-DryRun`.
