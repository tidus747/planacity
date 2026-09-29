# Create, edit, save, and reopen a plan

Install and run from source using [the README](../README.md#run-from-source).
No account or network connection is needed while planning.

1. Choose **File -> New plan...** (`Ctrl+N`). Enter a name and choose an inclusive
   date range from the calendar controls. You can also type dates in `YYYY-MM-DD`
   form. A plan can span any dates, not only a quarter.
2. Open **Plan**. Add an Epic, select it and add a Task, then select that Task and
   add a Subtask. With no Epic selected, Add Task creates a standalone Task.
3. Double-click a title, estimate, start, or end cell, or press `F2` to edit.
   Estimates use hours, including fractional hours. Clear a value to leave it
   unset; zero hours is different from unknown. Invalid drafts stay editable;
   correct them or press `Escape` to cancel.
4. Use **Move...** to select a different parent. **Delete...** previews the number
   of work items, relationships, and memberships being removed before confirming.
5. Use **WorkGroups...** to organize Epics independently from hierarchy. Use
   **Relationships...** to add `related_to`, `depends_on`, or `blocks` links.
   Links do not automatically reschedule work. Dates outside the horizon are
   retained and shown in the Planning notes column.
6. Open **People** to add, rename, or remove roster members. Assignments, load
   calculations, and recurring capacity reservations are planned for v0.4.
7. Open **Timeline** (`Ctrl+3`) for a read-only view of scheduled bars across the
   planning horizon. Start-only, end-only, unscheduled, and outside-horizon work
   remain visible as explicit schedule states. Timeline selection and scrolling
   do not change the plan.
8. Choose **File -> Save** (`Ctrl+S`) and select a `.planacity` path. **Save As**
   (`Ctrl+Shift+S`) saves a separate project. The window title shows `*` while
   changes are unsaved. Cancelled or failed saves retain the current draft.
9. Close Planacity, launch it again, then use **File -> Open...** (`Ctrl+O`) to
   reopen the project. Continue editing and save again.

New, Open, Restore, and Exit ask whether to save, discard, or cancel when the
current plan has unsaved changes. **File -> Plan properties...** edits the name,
description, and horizon. Both appearances remain available from the sidebar and
**View -> Appearance**; this preference is stored separately from project data.

## Try the fictional example

Use **File -> Restore JSON backup...** and choose
`examples/aurora.planacity.json`. It opens as an unsaved copy, preserving the sample
file. Save it to a new `.planacity` path. The sample contains two Epics, Tasks and
Subtasks, three people, hour estimates, dates, a WorkGroup, and dependencies.
Missing estimates/dates are intentional examples of incomplete planning data.

Use **File -> Export JSON backup...** for a portable backup. See
[project-file-format.md](project-file-format.md) for validation and recovery.

## Validation record

For the v0.2 workflow, see [Jira CSV import](jira-import.md) and
[Jira CSV export](jira-export.md). Imported baselines survive local edits and
save/reopen; use Changes (Ctrl+6) to review differences.

On Windows, Python 3.12 and PySide6 6.11.2, automated tests exercise new-plan
validation, hierarchy editing, invalid inline drafts, People/WorkGroup/link forms,
Ctrl+S, Save As, cancellation, close/reopen/continue, and JSON backup/restore.
The GUI acceptance tests also pass with Qt's native `windows` platform plugin,
in addition to the offscreen CI tests. Both appearances were visually inspected
using the fictional example; screenshots are included below.

This is a source preview, not a packaged release. Installer and broader usability
testing remain release work. No release tag or application download is published.

![Plan workspace in light appearance](images/plan-light.png)

![Plan workspace in dark appearance](images/plan-dark.png)
