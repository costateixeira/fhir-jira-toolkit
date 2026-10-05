---
description: Update the ticket progress chart (burn-up per iteration) from the latest JIRA export – asks whether this is a new iteration or the same one, logs what changed, and opens the chart.
argument-hint: [new | same] [path to export or config]
---

Update the progress chart for the tickets tracked in this repository. Arguments: **$ARGUMENTS**

The chart is a stacked bar per *iteration* (the user decides what an iteration
is – never one bar per day or per check). Categories, bottom to top: Applied
(marked in JIRA), Done (applied in the specification but not marked Applied),
In PR, Voted (not applied), Disposition (not voted), No disposition.

1. **Configuration.** Use `.jira-cache/progress-config.json` (or the path given).
   If it does not exist, create it with the user:
   - `title`; `export`: a glob for the JIRA CSV exports (the newest is used);
   - `github` (org/repo, so open and merged PRs are read from their titles) with
     `pr_since` (the date the work started) and, if needed, `pr_ignore`;
   - `extra` (tickets not in the export, e.g. in another specification) and
     `exclude`;
   - `done_not_marked` (applied earlier, not marked Applied),
     `voted_not_entered` (voted in a meeting, not yet in JIRA),
     `dispositions_local` (disposition drafted locally, not yet in JIRA).
   Suggest the JIRA filter and columns for the export: project, work group,
   specification(s), `status in (Submitted, Triaged, "Waiting for Input",
   "Resolved - change required") OR status changed to Applied after "<start>"`;
   columns Issue key, Summary, Status, Resolution, Resolution Description,
   Specification (plus Resolution Vote / Vote Date if available).
2. **Compare** the newest export with the previous one (the one used for the
   last iteration): new and removed tickets, status and resolution changes.
   Check open/merged PRs. Update the config lists for anything JIRA cannot know
   (a ticket checked and confirmed as applied but not marked; a vote not
   entered; a disposition drafted locally).
3. **Ask the user** whether this update is a **new iteration** or the **same**
   iteration as the last bar, unless the argument says it (`new` / `same`).
4. Run the chart script:

   ```bash
   python3 "${FHIR_JIRA_PLUGIN_ROOT}/skills/fhir-jira-workflow/scripts/progress_chart.py" \
     <new|same> --config .jira-cache/progress-config.json [--date YYYY-MM-DD]
   ```

   It writes `progress-data.json`, `progress.md` (tickets per category),
   `progress.html` (single file, reloads every 30 s) and a copy per iteration in
   `progress-history/`. Use `show` to see the counts without saving.
5. **Log the iteration** in `.jira-cache/progress-history/evolution.md`: source
   export, counts, what changed and why (tickets that moved between categories,
   PRs merged, votes, new tickets), and any change to how tickets are counted.
   The user documents the evolution later from this log.
6. Open `progress.html` in the user's browser and report the counts (previous
   iteration → this one) in a short table.

A baseline bar for a date before the tracking started can be added by hand to
`progress-data.json` with `"iteration": 0` and `"note": "reconstructed"` (shown
as `#0*`); describe the reconstruction in the evolution log.

Related: `scripts/wiki2html.py <in.md> <out.html>` converts the JIRA/Confluence
wiki markup used for agendas and dispositions to HTML that can be copied from
the browser and pasted into the Confluence editor (tables, links, lists).
