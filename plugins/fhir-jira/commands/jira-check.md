---
description: Check whether a resolved HL7 FHIR JIRA ticket is effectively applied in a build – shows the ticket and the updated page(s), and gives an opinion for the user's final review.
argument-hint: <FHIR-NNNN> [master | branch:<name> | local] [page#anchor ...]
---

Check whether HL7 FHIR JIRA ticket **$ARGUMENTS** is applied in the current build.

This is a read-only check: do not edit, commit or push anything.

1. Run the version currency preflight from the `fhir-jira-workflow` skill.
2. Fetch the ticket with `scripts/fetch_ticket.py` into a staging cache (as in
   the workflow, step 1) and resolve its repository with `scripts/resolve_repo.py`.
3. Read the ticket's Resolution Description and write a short checklist of what
   must be visible in the specification (texts, elements, codes, examples,
   release-note entry). Use local notes only to locate the change, never to
   widen it (Jira's resolution is authoritative).
4. Find the page(s): the pages given in the arguments; otherwise the ticket's
   Related URL; otherwise derive them from the resolution (resource page,
   `-definitions.html#<Element>` for element changes, examples page, search
   page). Find the PR or commit that applied the ticket (`git log --all
   --grep <KEY>`, `gh pr list --search <KEY>`) to know which files and texts
   changed and whether it is merged.
5. Choose the build: `master` (https://build.fhir.org/, merged changes) when the
   PR is merged; `branch:<name>` when https://build.fhir.org/branches/<name>/
   exists; otherwise `local` (`publish/` for FHIR Core, `output/` for IGs –
   only valid if it was built from the branch that contains the change). The
   argument overrides this.
6. Run the evidence script and open the browser window: the JIRA ticket, the
   inspected pages and the **file diff of the PR(s)** that applied the ticket
   (`--pr`, repeatable). Always include the PR diff tab, and give its link
   (`https://github.com/<org>/<repo>/pull/<N>/files`) in the reply as well:

   ```bash
   python3 "${FHIR_JIRA_PLUGIN_ROOT}/skills/fhir-jira-workflow/scripts/check_applied.py" \
     --ticket-json <staging>/FHIR-NNNN.json \
     --page <page>.html#<anchor> [--page ...] \
     --expect "<text that must appear>" [--expect ...] \
     --absent "<text that must be gone>" [--absent ...] \
     --source <master|branch:NAME|local> --open \
     --out .jira-cache/jira-check/FHIR-NNNN.md
   ```

7. Compare the evidence with the checklist and give an **opinion**, clearly
   marked as subject to the user's final review:
   - **Applied** – every checklist item is visible in the build;
   - **Partly applied** – list what is missing;
   - **Not applied** – the build does not show the change (say whether the PR
     is unmerged, or the build is older than the merge);
   - **Unclear** – say what could not be checked and why.
   Note any deviations from the resolution text (for example edited wording).
8. Write the opinion into the Verdict section of
   `.jira-cache/jira-check/FHIR-NNNN.md`, and if an apply plan with a progress
   tracker exists, note the check result in the ticket's row.
9. Ask the user for the verdict and give the Jira closing comment, for example
   `Applied in [PR 4326|https://github.com/HL7/fhir/pull/4326]` (several PRs:
   `… and [PR nnnn|…]`; a ticket that needed no change: say why, e.g. "No longer
   applicable: …"). Append the user's verdict to the report
   (`**User verdict:** Confirmed – applied (<date>)`, or *Pending*, or
   *to be confirmed by the work group*) and add the comment to
   `.jira-cache/jira-closing-comments.md` (Jira markup, grouped by batch), ready
   to paste when the ticket is marked Applied.

## Checking several tickets (guided review)

When the user asks to check a set of tickets (for example all tickets of a
merged PR, or of several PRs merged together), present them **one at a time**:
open the browser window for one ticket, give the evidence, the opinion and the
Jira comment, and wait for the user's verdict before opening the next. Do not
write the user's verdict yourself; "move to next" without a verdict means
*Pending*. Tickets the user wants the work group to confirm go to the meeting
agenda as a confirmation item, and stay *Pending*.

After a merge, `build.fhir.org` (master) is rebuilt after some delay, and the
online build can include some merges but not the latest ones. Before checking,
confirm that each ticket's change is in the online build (for example its
release-note entry, or a new page); if not, wait (poll every few minutes) or,
if the user prefers, check a local build of the default branch and say so in
the report. Prepare the evidence while waiting, so the checks can be shown as
soon as the build is updated.
