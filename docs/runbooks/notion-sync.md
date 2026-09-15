# Runbook — Notion project sync

Keeps the Notion **Projects Database** current without anyone editing it by hand.

## What it does

On every push to `main` that touches `mlops/ROADMAP.md` or `mlops/docs/decisions/`,
`scripts/sync_notion.py` parses the roadmap, works out the current phase and how many
items are complete, counts the decision records, and writes four properties onto the
Notion project page: **Current Phase**, **Phase Progress**, **ADRs**, **Last Synced**.
It also stamps **Sync Source** so the page says where its numbers came from.

## Direction of truth

The flow is one-way: **repository → Notion**. The script never reads state back out of
Notion, so the two stores cannot disagree about who is right, and there is nothing to
merge. Two-way sync between databases is how you get duplicated state and silent
overwrites; it is deliberately not built here.

Consequence: **do not edit the synced properties in Notion.** Anything typed into them
is overwritten on the next push. Properties the script does not touch — Status, Area,
Summary, Started, Sessions, and the page body — are yours and are never modified.

## One-time setup

**1. Create the Notion integration**

In Notion: Settings → Connections → Develop or manage integrations → New integration.
Internal integration, this workspace, with content capabilities. Copy the secret; it is
shown once.

**2. Share the database with it**

Open the Projects Database, then the `···` menu → Connections → add the integration.
This step is the one people forget. Without it the API returns 404 on a page that plainly
exists, because the integration cannot see it.

**3. Add the repository credentials**

In GitHub → Settings → Secrets and variables → Actions:

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `NOTION_TOKEN` | the integration secret from step 1 |
| Variable | `NOTION_PROJECT_PAGE_ID` | the BankML Platform page ID |

The page ID is the 32-character string in the page URL, with or without dashes. The token
is a secret; the page ID is not, and is a variable rather than a secret so it shows up in
logs when something goes wrong.

**4. Run it once by hand**

Actions → Sync project state to Notion → Run workflow. Check that the Notion page changed.

## Running locally

```bash
python3 scripts/sync_notion.py --dry-run          # parse and print, sends nothing
NOTION_TOKEN=... NOTION_PROJECT_PAGE_ID=... python3 scripts/sync_notion.py
```

Standard library only, so there is nothing to install.

## Failure modes

| Symptom | Cause |
| --- | --- |
| `No phase headers found` | A roadmap heading stopped matching `## Phase N — Title`. The em dash matters. |
| Notion rejects with 404 | The integration was never added to the database in step 2. |
| Notion rejects with 401 | The token is wrong, or was regenerated in Notion and not updated in GitHub. |
| Notion rejects with 400 | A property was renamed in Notion. The script writes by property name. |
| Counts look wrong | A roadmap item is not a `- [ ]` or `- [x]` checkbox, so it is not counted. |

The workflow runs `--dry-run` before the real call, so a parsing problem fails the build
without touching Notion.

## Extending it

The obvious next additions, in order of usefulness:

- Create a Notion page per ADR, so decisions are browsable from the Knowledge database
- Write the CI status of the last run onto the project page
- Post a comment on the Notion page when a phase's exit criteria all turn green

Each of these is still one-way. Keep it that way.
