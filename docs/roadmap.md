# Planacity implementation roadmap

Revised 2026-10-04 after the planning and demonstration review.
This is the implementation direction, not a list of features already available
or a release announcement. Current source remains `0.4.0.dev0`, file schema 8.

The next useful outcome is: "I can explain whether this plan fits the team,
where its capacity goes, and which assumptions still need attention."

## What the review found

The repository has the required foundations: work hierarchy, Jira CSV roundtrip,
Timeline date editing and arrows, calendars, availability, recurring reservations,
and explicit multi-person work allocations. The pieces need a shared calculation
and a clearer editing workflow before more charts can be trusted.

The table records the original review findings; see tracking below for progress.

| Observation | Behavior at review | Decision |
| --- | --- | --- |
| Overview cannot explain spare capacity or topics | Counts work and roster entries only | Add a compact analysis selector after shared capacity totals exist |
| Estimate calendar cannot be selected | Disabled for Hours; Days/Weeks list existing work calendars | Explain the state and offer calendar setup from the dialog; verify the reported failure |
| Epic effort does not follow its tasks | Parent and child estimates are independent | Derived leaf-effort totals, with partial/unknown states and safe handling of legacy parent effort |
| Allocations can exceed a person's calendar | Stored hours have no time distribution or capacity comparison | One dated calculation and actionable warnings across views |
| Plan's right panel is mostly informational | WorkItem has no description or labels | A real inspector with explicit Apply/Cancel and persisted metadata |
| Timeline can violate a predecessor's dates | Conflicts appear in dependency text but do not block date edits | Guard date edits in the planning layer, including keyboard and drag paths |
| Dependency details are difficult to scan | Text and Gantt arrows | A small selected-item graph with dates and assigned people |
| Meetings and front office are hard to find | Deductions appear inside the reservation wizard, not the People totals | Show the same breakdown in People, Overview, and a team Timeline mode |
| Absences lack Timeline context | Stored availability has no Timeline overlay | Optional named, hatched absence lanes using existing data |

The calendar-selector cause is a code finding, not confirmation of the exact
user-reported failure. The reproduction matrix below remains required.

## Release sequence

Keep the existing minor-version sequence. Finish a useful v0.4 before expanding
the calendar model. Deliver through small PRs in the order below; review each
wave in the running application before starting the next.

| Release / wave | User outcome | Required slices |
| --- | --- | --- |
| v0.4 A - Reliable editing | Configure effort units and trust hierarchy/dependency edits | R01-R03 |
| v0.4 B - Explainable capacity | See hours consumed by duties and work, with missing-data and overload findings | R04-R06 |
| v0.4 C - Understand the plan | Edit context and topics; inspect workload and effort distribution in Overview | R07-R09 |
| v0.4 D - Review and demonstrate | See People groups, edit/map priorities, and explore the Moon Heist example | R10, P01-P02, D01 |
| v0.5 A - Team visibility | See people, absences, duties, dependency graphs, and critical paths in Timeline | V01-V06 |
| v0.5 B - Program Calendar | Add shared holidays/events and file-based availability providers | Calendar slices below |
| v0.6 - Milestones & Deliveries | Model outcomes, readiness links, and risk as first-class entities | Preserve the existing milestone goal |
| v0.7 - Communication | Share the now-trustworthy Timeline, capacity, calendar, and Program Pack | Export before more dashboard variants |
| v0.8 - Scenarios & Reconciliation | Compare plans and reconcile Jira re-imports without losing baselines | Preserve deltas and explicit conflict resolution |
| v0.9 - Stabilisation | Improve large-plan performance, migrations, keyboard use, and installers | No major product features |
| v1.0 - Stable | Reliably import, plan, allocate, validate, communicate, and export | Full workflow acceptance |

v0.5 A uses current availability and reservation data. It does not wait for
Factorial, a generic CalendarEvent model, or HR imports. The compact Overview
charts move forward from the broad v0.7 communication goal into v0.4 because
they are needed to validate a plan inside the application. External report
generation stays in v0.7. Packaging smoke checks and error handling accompany
each release; v0.9 is not the first time they are tested.

## v0.4 implementation slices

These are backlog keys, not GitHub issue numbers. Promote the next wave to
focused GitHub issues linked to the v0.4 milestone when implementation resumes.
GitHub owns live status; this document owns scope, ordering, and acceptance.
R01 was completed in [#75](https://github.com/tidus747/planacity/issues/75) and
merged through [#76](https://github.com/tidus747/planacity/pull/76). R02 was
completed in [#77](https://github.com/tidus747/planacity/issues/77) and merged
through [#80](https://github.com/tidus747/planacity/pull/80). Website showcase
work (#78) merged through PR #79. R03 was completed in
[#82](https://github.com/tidus747/planacity/issues/82) and merged through
[PR #83](https://github.com/tidus747/planacity/pull/83). R04 was completed in
[#88](https://github.com/tidus747/planacity/issues/88) and merged through
[PR #89](https://github.com/tidus747/planacity/pull/89). R05 was completed in
[#90](https://github.com/tidus747/planacity/issues/90) and merged through
[PR #91](https://github.com/tidus747/planacity/pull/91). R06 was completed in
[#92](https://github.com/tidus747/planacity/issues/92) and merged through
[PR #93](https://github.com/tidus747/planacity/pull/93). R07 was completed in
[#94](https://github.com/tidus747/planacity/issues/94) and merged through
[PR #95](https://github.com/tidus747/planacity/pull/95). R08 was completed in
[#96](https://github.com/tidus747/planacity/issues/96) and merged through
[PR #97](https://github.com/tidus747/planacity/pull/97). R09 was completed in
[#98](https://github.com/tidus747/planacity/issues/98) and merged through
[PR #99](https://github.com/tidus747/planacity/pull/99). R10 is tracked in
[#100](https://github.com/tidus747/planacity/issues/100). Later slices remain planned.
The [implementation queue](implementation-queue.md) adds focused briefs,
dependencies, and review evidence for the next sessions.

### R01 - Make estimate-calendar setup understandable

Priority: first. Dependencies: none.

- Explain that Hours needs no reference calendar. Days/Weeks must enable the
  selector and list saved calendars by name; never silently assume 8-hour days.
- Offer Create/manage calendars from the dialog, then refresh choices and keep
  the selected unit. Cancelling unit changes must not silently save a calendar
  draft; explicitly confirmed calendar changes have their own clear boundary.
- Identify calendars with no positive hours and explain why they cannot be used.
  Keep the effort-conversion calendar distinct from each person's work calendar.
- Reproduce with an empty plan, the example, one/multiple calendars, Hours,
  Days, Weeks, reopened projects, native Windows, keyboard, and both themes.
  Diagnose separately if a valid calendar still cannot be selected.

### R02 - Guard dependency changes and date edits

Dependencies: none. See the [decision record](planning-decisions.md).

- One pure validator normalizes `depends_on` and `blocks` to predecessor ->
  successor. At day resolution, predecessor end must be before successor start.
- Reject date edits creating or worsening a conflict, including resizing the
  predecessor's end, successor's start, and Plan/Timeline keyboard editors.
  Show the affected work, dates, and earliest permitted boundary before applying.
- Permit old inconsistent/imported plans to open and be repaired. Missing dates
  are an explicit unevaluated finding. Reject new cycles; retain imported cycles
  visibly. No automatic cascade or silent date changes.
- Test reversed relationship storage, equality at the boundary, hidden endpoints,
  cycles, multiple prerequisites, unrelated existing conflicts, and cancellation.

### R03 - Roll up hierarchy effort without double counting

Dependencies: none; required before capacity and Overview totals.

- A leaf uses its entered estimate. An Epic with Tasks, or a Task with Subtasks,
  displays the sum of its leaf estimates, read-only in the estimate column.
  Show known subtotal plus missing-estimate count instead of treating unknown as 0.
- Sum allocations once by allocation ID. Show estimated and allocated effort as
  separate values; these are planned hours, never time spent or productivity.
- Preserve imported/manual parent estimates as reference values. Existing direct
  parent allocations remain visible and counted until explicitly resolved.
  Adding children to allocated work requires the resolution preview described
  in the decision record; no silent loss or reassignment.
- Verify nested Subtasks, zero/unknown estimates, reparent/delete, legacy files,
  and display-unit conversion. Derived totals never silently replace Jira export
  estimates or baseline data; export preview explains which values it uses.

### R04 - Build the shared dated capacity calculation

Dependencies: R03. Domain/services and calculation tests only in this slice.

- Combine each person's calendar, availability, recurring reservations, and
  dated work allocations into one queryable result for any inclusive date range.
- Use the full work window and complete reservation periods before clipping to
  the visible range. Preserve reservation proration and exact hour conservation.
- Expose nominal, unavailable, reserved (by rule), planning, allocated, and
  remaining hours, plus demand that cannot be placed and missing-input findings.
- Sum simultaneous work per person. Never turn missing calendars/dates into zero
  demand or positive free capacity; retain negative remaining hours.
- Test variable days, overlapping work/absences/reservations, zero capacity,
  partial periods, dates outside the horizon, and deterministic rounding.

### R05 - Surface planning findings during editing

Dependencies: R02-R04.

- Reusable findings have a stable rule key, severity, affected IDs/date range,
  explanation, and suggested action. Compute them from the current snapshot.
- Show icon plus text for missing calendar, missing dates/estimate, unallocated
  work, allocation/estimate mismatch, mixed hierarchy effort, and overload.
  Display in Plan rows, its detail panel, and the allocation draft preview.
- Compare against all concurrent assignments, not only the selected task. A
  100-hour task split between two people is not 100 hours for each person.
- Allow saving a capacity-infeasible draft with visible findings. Dependency
  edit rejection follows R02. Findings refresh after calendar, absence, duty,
  date, hierarchy, and allocation edits without rewriting estimates.

### R06 - Give People a complete capacity breakdown

Dependencies: R04-R05. First visual acceptance checkpoint for the shared engine.

- Extend the existing People page with day/week/selected-period capacity, work,
  reservations, and signed remaining hours; avoid another top-level page initially.
- Selected-person details list meetings/front office by saved rule name and the
  allocated tasks responsible for each period. Links open the relevant editors.
- Include zero-allocation roster members, unknown calendars, fully unavailable
  periods, and demand without dates. Identify the data that prevents a conclusion.
- Test that wizard, People, and Plan use identical totals for the same interval.
  Include a compact load heatmap with text values and an accessible table.

### R07 - Persist work context and a primary reporting topic

Dependencies: R03.

- Add plain-text description, labels, and an optional primary WorkGroup selection
  with validation, services, SQLite/JSON migration, and deletion/reference handling.
- Use the topic inheritance and legacy multi-group rules in the decision record.
  Standalone tasks must be classifiable. Multi-valued labels remain separate.
- Show legacy missing metadata as empty, preserve IDs and user text, and keep
  imported raw data/baselines intact. No implicit Jira label mapping.
- Schema 8 persists the new fields. Schemas 1-7 load them as empty without
  rewriting the source file; the next save upgrades the complete document.

### R08 - Turn the right-hand panel into a work inspector

Dependencies: R05, R07.

- Selecting work exposes title, description, labels, primary group, dates,
  entered/rolled-up estimates, people with allocated hours, and dependencies.
- Use explicit Apply/Cancel, inline validation, and Save/Discard/Cancel when
  selection changes with a draft. Never save half of a multi-field edit.
- Reuse canonical editing services and the calendar/units conventions. Preserve
  selection and filters, keyboard access, readable light/dark states, and no-op
  edits. Imported reference values are identified separately from editable work.

### R09 - Add a small analysis selector to Program overview

Dependencies: R03-R08.

- Keep the summary cards. Add a collapsible Analysis section with a selector:
  Capacity by person / Planned work by topic / Capacity breakdown.
- Use horizontal bars with exact values and a table alternative. Show meetings,
  front office, unavailability, work, and remaining hours separately. Display
  overload outside the normal bar extent; do not hide it in a clipped percentage.
- Topic view defaults to scheduled allocated hours in the selected interval.
  Offer estimated leaf effort as a separately labelled measure. Include Ungrouped,
  Ambiguous group, unplaced demand, and incomplete-data explanations.
- Charts must reconcile to R04/R06. Filters cannot hide other work competing for
  the same person's capacity. State the date range, scope, and workload coverage.
- Native Qt painting, keyboard-accessible values, and no new chart runtime.

### v0.4 acceptance gate

The October review adds R10 (People work groups) after R06/R07 and P01/P02
(priorities and CSV mapping) after the inspector. These are separate PRs, not
extra acceptance criteria silently added to R06 or R08. Finish the existing
R03-R09 sequence first, then R10, P01, P02, and the D01 demonstration dataset.
See the implementation queue for their acceptance criteria. D01 ships only
implemented fields; graph and critical-path exercises are later extensions.

Evaluate a fictional program with an Epic of two Tasks (60 h and 40 h), two people
with different calendars, a full absence, meetings, front office, overlapping
work, one missing estimate/calendar, and a dependency. The Epic shows 100 h only
when all leaf estimates are known. The shared engine explains each person's
remaining hours and overloads. Overview matches People and allocation previews.
Invalid dependency edits retain the prior dates. Save/reopen and JSON restore
preserve data; Jira baseline/export conventions remain explicit.

Record native Windows and both-theme acceptance, regression tests, migration
checks, and package/website builds. Update public website copy to distinguish
implemented features from the remaining roadmap. This planning change does not
edit the Astro site or publish a new release. v0.4 is not complete merely because
the previous issue queue is empty; release approval follows this acceptance gate.

## v0.5 visual work, before new calendar providers

| Key | Slice | Depends on | Acceptance |
| --- | --- | --- | --- |
| V01 | Team coverage in the Timeline summary | R04-R06 | Count distinct people with positive planned allocations; show roster coverage, unscheduled demand, and incomplete data. Filters distinguish visible from whole-plan counts. No productivity judgement. |
| V02 | Optional unavailability overlay | Existing availability, R04 | Toggle off by default; named person lanes with hatched rectangles, dates and partial/full share. Clip visibly, retain canonical dates, support both themes and keyboard details. |
| V03 | Plan / Team Timeline modes | R04-R06, V01-V02 | Team mode has one person section with work, absence, and duty lanes. Show reservation names/hours by period and weekly load, not fictitious meeting appointments. Toggling views changes no data. |
| V04 | Selected-work dependency graph | R02, R03, R08 | Immediate predecessors -> selected work -> immediate successors. Cards show title, dates, assigned people and warnings; click to select/recenter. Graph cycles and hidden endpoints remain explicit; text details stay available. |
| V05 | Critical-path calculation | R02, R03 | Pure elapsed-day CPM service with explicit assumptions, float, all tied critical paths, and incomplete/unsupported results. See the decision record. |
| V06 | Critical-path Timeline overlay | V04, V05 | Optional red critical connectors and labelled task outlines, readable in both themes. Filters do not recalculate criticality. Keyboard details expose float and coverage. |

Use existing Qt graphics for V04. Start with immediate neighbours and a bounded
view, not a full-program layout engine. Show when nodes are omitted and allow
navigation to their list. No Graphviz executable, browser, Mermaid runtime, or
network service is required. Parent/child hierarchy is not a dependency edge.

### Complete the v0.5 Program Calendar goal

Implement V04 before V05/V06 so the selected-item graph is useful independently
of critical-path analysis. Priority does not determine criticality. These new
slices remain in v0.5; they do not delay the v0.4 capacity acceptance gate.

After V01-V06, split work into separate issues in this order:

1. Shared holiday and program-event domain, capacity effects, persistence, and
   overlap policy. Reuse the R04 calculation boundary; avoid double deductions.
2. Program Calendar editing and projection into Timeline/Overview. A capacity
   reservation is not an absence or an all-day event.
3. Generic availability CSV preview, people matching, and duplicate detection.
4. Factorial exported-file mapping as an adapter to that same import workflow.
   Keep absence reasons out of planning files unless strictly needed.
5. Optional Jira CSV description/label mapping, including an explicit mapping of
   primary WorkGroups to labels. Preview escaping, unsupported values, and existing
   labels; never silently replace them or assume a Jira API integration.

## Optional external-assistant workflow

The [agent-assisted planning proposal](agent-assisted-planning.md) defines a
versioned, offline guide reachable from Help and About. External tools prepare a
JSON proposal; Planacity validates and reviews it before the user saves a copy.
Application version, writer schema and guide revision travel together. This
does not introduce an embedded assistant or change the local-first data model.

Target A01/A02 for v0.5 as separate slices: packaged guide contract, then the
Help/About interface using existing Export/Restore. Keep the current v0.4
sequence unchanged. A03 is a later, optional proposal-review and planning-kit
enhancement, scheduled after feedback on the guide; it is not a v0.5 release
gate. These slices do not block visual planning or new calendar providers.
Acceptance and dependencies are in the
[implementation queue](implementation-queue.md). Every release after the feature
ships must verify guide compatibility, even without a schema bump.

## Scope and delivery discipline

Preserve local/offline use, one canonical ProgramPlan, and the existing Python/Qt
stack. No automatic resource levelling, actual-time tracking, arbitrary chart
builder, AI scheduler, cloud service, Jira API, or full graph editor is required
for this roadmap. Do not infer person assignment from imported Jira assignees.

Each issue needs a complete testable outcome and its own review. Calculation
rules are defined in [planning decisions](planning-decisions.md); current behavior
is documented in [architecture](architecture.md), [capacity](capacity-model.md),
and [allocations](allocation-model.md). New UI screenshots and website claims
follow implementation, not mockups presented as working features.
