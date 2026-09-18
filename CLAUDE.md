# AI Infrastructure Lab — working conventions

Conventions for this entire repository. Project-specific rules live in that project's own
`CLAUDE.md`; see `mlops/CLAUDE.md` for BankML Platform, whose rules are additional to these,
never in place of them.

---

## Standard

This repository is a professional engineering portfolio, read by technical recruiters and
engineers. Everything produced for it is written to that standard.

**No emoji. Anywhere.** Not in documentation, not in commit messages, not in code comments,
not in Notion pages, and not as status indicators in tables. Write `In progress`, never a
coloured square. This applies to every artifact, including ones written into Notion.

Arrows (`→`) and box-drawing characters in ASCII diagrams are technical notation rather than
decoration, and are fine.

Prose is plain, specific and declarative. No marketing language, no filler, no exclamation
marks. State what a thing does, what it costs, and what it does not do. A known limitation
written down is worth more than a claim that papers over it.

---

## Git

**Claude never runs a mutating Git command.** Not `add`, `commit`, `push`, `pull`, `fetch`,
`merge`, `rebase`, `checkout`, `branch` (create or delete), `stash`, or `reset`, and no `gh`
command of any kind. Every Git operation that changes history, the working tree, a branch, or a
remote is run by the repository owner, by hand, in his own terminal — that hands-on practice is
the point, not a limit on what Claude is capable of.

Read-only Git commands (`status`, `log`, `diff`, `show`, `branch -v` and the like) are fine for
Claude to run when they are the fastest way to check state. When work is ready to commit, stop
and say so, and propose a commit message. Do not offer to run it.

---

## Commits

Commit subjects are a plain imperative sentence in normal English. **No type prefixes, no
scopes, no colons, no tags.**

```
Add as-of aggregation for bureau balance
Propagate request id into the prediction log
Fix sentinel handling in DAYS_EMPLOYED
```

Not `feat(features): ...`, not `docs: ...`, not `[MLOPS] ...`.

Subject under roughly 70 characters. Reasoning goes in the body after a blank line.

**Never add `Co-Authored-By` trailers, `Generated with` lines, tool URLs, or any other
attribution footer** to commits or pull request descriptions.

Commit in small, coherent increments. One logical change per commit. Do not batch unrelated
work into a single large commit.

Branch names are short and descriptive, with no prefixes: `as-of-bureau-aggregation`,
`proxmox-network-bridge`.

---

## Work sessions

Work is logged in the Notion **Sessions Database**, one page per session. Several sessions
can be open at the same time — one for MLOps, another for networking — so the active session
is **resolved, never assumed**.

### Resolving the active session

Before making changes, at the start of a working session:

1. Query the Sessions Database for rows whose Status is `In progress`.
2. Match them against the area of the repository being worked in, using the table below.
3. **Exactly one match:** that is the active session. State which one, then continue.
4. **More than one match:** ask which. Never guess, and never pick the most recent.
5. **No match:** ask whether to open a new session. Do not create one unprompted.

State the resolved session once, at the start. Do not re-announce it on every change.

### Repository path to area

| Path | Area | Project |
| --- | --- | --- |
| `mlops/` | MLOps | BankML Platform |
| `infrastructure/` | AI Infrastructure | |
| `containers/` | Containers | |
| `automation/`, `scripts/`, `.github/` | Automation | |
| `monitoring/` | AI Infrastructure | |
| `labs/` | depends on the lab — ask | |

A change touching several areas belongs to the session whose area owns the **purpose** of the
change, not the one with the most files touched. Editing `.github/workflows/` to add CI for
BankML is MLOps work, not Automation work.

### Opening a session

Create the page from the **Default Session** template so the structure stays consistent.
Set `Session`, `Session ID` (next in sequence), `Date`, `Area`, `Project` where one applies,
`Difficulty`, `Priority`, `Environment`, `Repository`, and Status `In progress`.

A session spanning several days uses a date range rather than a new page. One session is one
piece of work, not one sitting.

### Closing a session

Fill in the template sections from what was actually done — not from what was planned. In
particular:

- **Problems Encountered** records the error as it appeared, with the exact message.
- **Solutions** records what fixed it and why it was broken. The why is the part worth reading
  in six months.
- **Repository State** lists the commits the session produced.
- **Concepts Learned** is the canonical list. A concept that earns its own page is linked
  through the Knowledge relation; it is not retyped in two places.
- Interview questions are created as pages in the Interview Database and linked through the
  relation. They are never listed inline in the session page.

Then set Status `Done` and `Outcome` honestly. A session that ran out of time is `Partial`,
not `Success`.

### What never happens without being asked

- Never mark a session `Done`. Propose it; the owner decides when work is finished.
- Never create a session page unprompted.
- Never edit a session page belonging to a different area than the one being worked in.
- Never edit the Notion properties that the sync workflow owns — `Current Phase`,
  `Phase Progress`, `ADRs`, `Last Synced`, `Sync Source`. Those come from the repository via
  `scripts/sync_notion.py` and are overwritten on the next push. See
  `docs/runbooks/notion-sync.md`.

---

## Direction of truth

The **repository** is authoritative for project state: roadmap, phases, decisions, code, CI.

**Notion** is authoritative for the learning record: sessions, knowledge, interview
preparation, and the Status, Area and Summary of a project.

Sync runs one way only, repository to Notion. Nothing reads state back out of Notion into the
repository. When the two appear to disagree about project state, the repository is right.
