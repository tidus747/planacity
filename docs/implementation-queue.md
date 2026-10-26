# Implementation queue and review briefs

Planning revision: 2026-10-07. These are future implementation briefs, not
completed features. Read the [roadmap](roadmap.md) and
[calculation decisions](planning-decisions.md) together with this queue.
GitHub owns live status. Do not duplicate an existing issue or close it merely
because its specification is written here.

## Start the next session

1. Check main, the working tree, open issues, and pending PRs. R01-R10 and P01-P02
   are merged. Do not merge without maintainer approval.
2. Implement S01-S03 before selecting D01, the Moon Heist demonstration.
3. Turn each later brief into one issue with outcome, non-goals, dependencies,
   examples, persistence impact, and validation. Assign the release milestone.
4. Implement and review that slice alone, updating docs and user-facing changelog
   when appropriate. If it needs smaller PRs, define those boundaries first.
5. Include real visual evidence when applicable, then stop for review.

This planning session creates no runtime changes, sample JSON, migrations, or
release. Backlog keys below can become GitHub issues as their prerequisites land.

## Delivery order

| Target | Order | Outcome |
| --- | --- | --- |
| v0.4 foundations | R03 -> R04 -> R05 -> R06 | Trust estimates, workload, findings, and People totals |
| v0.4 context | R07 -> R08 -> R09 | Persist descriptions/topics, edit them, explain the plan |
| v0.4 finishing slices | R10 -> P01 -> P02 -> S01 -> S02 -> S03 -> D01 | Groups, priorities, single-person assignments, then the example |
| v0.5 visual planning | V07 -> V01 -> V02 -> V03 -> V04 -> V05 -> V06 | Visual identity, team visibility, dependency cards, critical paths |

This is a suggested serial order, not permission to implement the whole table
at once. Existing R03-R09 and V01-V04 acceptance criteria stay in the roadmap.
Dependencies below identify the minimum prerequisites; they are not hidden
additions to an issue already under review.

## R10 - Work groups in People

Target: v0.4. Depends on R06 and R07.

Outcome: selecting a person explains which work groups use their capacity.

- Derive associated groups from positive work allocations and effective WorkGroup
  context. No second manually maintained Person-to-WorkGroup membership model.
- Show group names in the roster and selected-person details. Add a WorkGroup
  filter and stable sorting by group names, then person name/ID. Keep one roster
  row per person, including people with several groups.
- Details link each group to its allocated tasks. Distinguish whole-plan
  associations from allocated hours within the selected date range.
- All inherited/context memberships can appear as navigation labels. Additive
  hour breakdowns use only the primary topic and exception buckets from R07.
- Keep ungrouped work, undated demand, and people without allocations visible.
  Filtering groups must not hide competing work from a person's capacity total.
- Verify legacy multi-person tasks, multiple groups, duplicate names, group deletion,
  child overrides, and a person working across groups. Counts use stable IDs.
- Evidence: People light/dark screenshots showing multiple groups and an empty
  association state; keyboard selection and filter walkthrough.

Non-goals: organizational teams, direct membership editing, Jira tag syncing,
new capacity rules, and summing a person's capacity once per group.

## P01 - Editable canonical work priority

Target: v0.4. Depends on R08. Separate from the description inspector PR.

- Add optional priority with ordered levels Highest, High, Medium, Low, Lowest.
  Unset is explicit; old work does not silently become Medium.
- Implement validation, services, the next actual SQLite/JSON migration, and
  backup compatibility. No preallocated schema version in this brief.
- Expose priority in the Plan column and inspector, with sorting/filtering,
  text labels and icons. Keep stable selection and existing draft semantics.
- Priority is an explicit planning decision, independent of dates, effort,
  hierarchy rollups, criticality, and person load. No automatic inheritance.
- Verify all levels, unset, clearing, save/reopen, legacy files, cancellation,
  and combined filters. Capture both themes with more than color as the cue.

Non-goals: priority schemes, automatic scheduling, arbitrary custom fields, and
Jira API calls. P02 owns external priority mapping.

## P02 - Explicit Jira CSV priority mapping

Target: v0.4. Depends on P01; reuse saved import/export mapping profiles.

- Let users map a CSV priority column and its distinct source values to P01.
  Offer exact default-name matches in a reviewable preview; custom names need
  a choice. Never interpret instance-specific numeric IDs as a universal order.
- Preserve original values and baseline snapshots. Unmapped or blank values
  remain visibly unmapped/unset; do not silently replace them with Medium.
- Export offers explicit target labels. Preserve unmapped source values for
  unchanged imported work; explain edited/unset values and conflicts in preview.
- Verify default and custom priorities, repeated/empty values, profile reuse,
  CSV escaping, changes detection, and baseline-preserving roundtrip.
- Evidence: mapping preview and its unresolved-value state.

Non-goals: administering Jira priority schemes or requiring Jira connectivity.

## D01 - Operation Moon Heist demonstration

Target: v0.4. Depends on R03-R10, P01, P02, and S01-S03.
Status: implemented by issue #118 with its reviewable feature PR.

Create the additive example and walkthrough from the
[scenario specification](moon-heist-example.md). Do not replace Aurora's legacy
migration fixture. Use the actual schema at implementation time.

Acceptance: deterministic IDs/dates and expected totals; valid dependencies;
single-person leaves with collaborative parent summaries; work groups;
descriptions; priorities; reservations; an
absence; save/reopen and a small CSV roundtrip. Keep a coherent initial plan and
separate documented exercises that introduce missing data or overload.
Capture real Overview, Plan, People, and Timeline images when available.
V04/V06 extend this same example later, without pretending those features exist.

## V04 - Visual dependency neighbourhood (existing scope)

Target: v0.5. Depends on R02, R03, and R08.
Tracked by [issue #130](https://github.com/tidus747/planacity/issues/130).

Keep the existing roadmap scope: selected item, immediate predecessors and
successors, dates, assigned people, findings, and keyboard/text navigation.
Show at most 30 cards and an explicit omitted-items list. Test cycles, partial
dates, long titles, legacy multiple allocations, aggregate parent teams, and
hidden endpoints. Use Qt directly.
Capture a branching graph in both themes. No full graph editor or CPM required.

## V05 - Critical-path analysis service

Target: v0.5. Depends on R02 and R03. Pure service and tests; no UI in this PR.
Tracked by [issue #132](https://github.com/tidus747/planacity/issues/132).
Implemented by [PR #133](https://github.com/tidus747/planacity/pull/133).

Implement the explicit analysis contract in the decision record. Return analysis
scope, completeness, durations, early/late offsets, total float, critical node
and edge IDs, and diagnostics. Never modify the plan or infer effort from dates.

Acceptance fixtures: one chain, a shorter parallel chain, two tied longest paths,
disconnected work, one-day tasks, duplicate/reversed edge storage, parent links,
cycles, missing dates, conflicting dates, and work outside the visible horizon.
Changing priority or a UI filter cannot change results. Empty input reports no
analysis, not a zero-day successfully planned program. No third-party runtime.

## V06 - Optional critical-path overlay

Target: v0.5. Depends on V04, V05, and V07's visual conventions.
Tracked by [issue #134](https://github.com/tidus747/planacity/issues/134).
Implemented by [PR #135](https://github.com/tidus747/planacity/pull/135).

- Add a clearly labelled toggle, off by default. Highlight critical connectors
  in red with a distinct line treatment and label/legend; outline critical bars.
- Show float and the analysis assumptions in keyboard-accessible details. Keep
  dependency violations visually distinct from valid critical relationships.
- Recompute after relevant committed date/hierarchy/relationship changes, never
  from the filtered view. Show hidden critical-item counts, tied paths, and
  incomplete/unsupported coverage. No stale overlay during an invalid result.
- Demonstrate the fork/join example from the decision record in both themes,
  with and without filters. Capture a short date-edit walkthrough.

Non-goals: moving work, leveling resources, a priority-based schedule, automatic
deadline promises, or claiming the analysis proves capacity feasibility.

## C01 - Shared calendar-event capacity foundation

Target: v0.5. Depends on R04. Tracked by
[issue #136](https://github.com/tidus747/planacity/issues/136).

Add one immutable shared CalendarEvent model with stable identity, category,
inclusive dates, and an exact unavailable fraction. Persist events in schema 12
and provide add/update/remove lifecycle services. Apply every event to every
roster person through their own calendar. Combine overlapping personal and shared
events using the strongest fraction, then apply reservations and allocations.

Accept full, partial, zero-impact, outside-horizon, overlapping, variable-calendar,
legacy migration, malformed-file, exact-precision, and no-mutation fixtures.
Keep imported snapshots unchanged and expose the same result through capacity,
reservation preview, and breakdown consumers.

Non-goals: Calendar UI, Timeline/Overview projection, recurrence, per-person event
targeting, generic CSV import, Factorial mapping, provider APIs, or automatic
holiday lookup.

## C02 - Manage shared program events

Target: v0.5. Depends on C01. Tracked by
[issue #142](https://github.com/tidus747/planacity/issues/142).

Add a dedicated Calendar workspace that lists every shared event and uses the
canonical lifecycle services to add, edit, and delete it. Keep strict ISO text
entry alongside the themed date picker. Show category, inclusive dates, exact
capacity impact, context-only events, and outside-horizon status. Editing retains
identity; deletion requires confirmation; cancellation and stale drafts change
nothing. No schema change is needed.

Acceptance includes deterministic ordering, keyboard navigation, both themes,
save/reopen and backup compatibility, unchanged imports, and cross-checking that
People/Overview consume the edited values through the existing capacity engine.

Non-goals: Timeline/Overview event projection, calendar-grid layouts, recurrence,
time-of-day, per-person targeting, file imports, provider APIs, and automatic
holiday lookup.

## C03 - Project shared events into Overview and Timeline

Target: v0.5. Depends on C02. Tracked by
[issue #144](https://github.com/tidus747/planacity/issues/144).

Project the schema 12 shared events without creating another editable model.
Overview lists horizon-intersecting events, exact impact, canonical dates, and
clipping status while counting retained outside-horizon events. Timeline offers
an off-by-default Program Calendar layer in both Plan and Team modes, aligned to
the same day, week, or month axis. Capacity-affecting and context-only events use
different line and fill treatments as well as text labels.

The projection sorts deterministically, clips only drawing coordinates, ignores
work filters, and never changes the plan. Editing remains in Calendar. Real
Overview and Timeline screenshots in both themes accompany the implementation.

Non-goals: editing outside Calendar, a month-grid calendar, recurrence,
time-of-day, time zones, per-person targeting, provider imports, capacity-rule
changes, and schema changes.

## C04 - Generic availability CSV preview service

Target: v0.5. Depends on C03. Tracked by
[issue #149](https://github.com/tidus747/planacity/issues/149).

Build the Qt-independent CSV reader, explicit field/person mappings, row-level
diagnostics, duplicate/overlap policy, versioned configuration-only profiles,
and immutable selected-row application. Raw HR rows remain transient. No schema
change or provider terminology enters the domain.

## C05 - Availability CSV review wizard

Target: v0.5. Depends on C04. Tracked by
[issue #150](https://github.com/tidus747/planacity/issues/150).

Expose C04 through Calendar with file selection, field and person mapping,
save/load profile actions, complete row review, explicit selection, confirmation,
and both-theme evidence. Factorial mapping remains the next adapter.

Status: completed by issue #150. Calendar now owns the UTF-8 file entry point,
delimiter choice, field and roster-person mapping, configuration-only profiles,
complete row review, explicit warning inclusion, and atomic confirmation.

## CJ01 - Reconcile Jira duty work with reserved capacity

Priority: high. Target: after the v0.5 Calendar foundation and before v0.8 Jira
reconciliation. Tracked by
[issue #161](https://github.com/tidus747/planacity/issues/161).

Prevent imported Meetings, Front Office, support, or similar Jira work from being
deducted both as a recurring reservation and as ordinary allocated work. Add an
explicit reservation-coverage link at Allocation level; never infer one from Jira
names, labels, types, or assignees. Preserve WorkItem and ReservationRule as
separate canonical entities.

Deliver this as focused slices: domain/calculation contract, persistence and
lifecycle rules, manual Plan/People editing, optional explicit Jira CSV mapping,
then shared breakdowns and findings. Report compatible covered hours, excess
work, unused reserved capacity, missing dates, non-overlapping periods, and
person/rule mismatches without silently changing estimates, dates, allocations,
reservations, or imported baselines.

Domain-link status: implemented by issue #164. ReservationCoverage explicitly
connects one allocation to one compatible reservation rule and validates stable
identity, uniqueness, references, and person membership without inference.
Persistence and lifecycle are implemented by issue #168 in schema 14. Capacity
reconciliation is implemented by issue #170: exact covered work consumes only
the selected rule's dated reservation, excess uses ordinary planning capacity,
and unused reserved hours remain visible. Manual Plan/People editing is
implemented by issue #172 with one explicit, person-compatible selector shared
by the allocation dialog and compact Plan inspector. Shared People/Overview
breakdowns and actionable partial/non-overlap findings are implemented by issue
#177. Optional Jira CSV mapping remains a focused slice of issue #161. It stays
deferred until import can bind explicit allocated hours: the current Jira import
preserves an assignee but deliberately creates no Allocation, so it has no valid
allocation-level object to cover and must not persist an inferred intent.

## C06 - Canonical sprint model and assignments

Target: v0.5. Tracked by
[issue #154](https://github.com/tidus747/planacity/issues/154), the first focused
slice of [#147](https://github.com/tidus747/planacity/issues/147).

Persist first-class sprints and separate leaf-work assignments in schema 13.
Support optional WorkGroup scope and diagnostics for overlaps, horizon bounds,
incomplete work dates, and work outside sprint dates. Do not add Calendar UI,
capacity calculations, Jira mapping, or automatic distribution in this slice.

Status: completed by issue #154 and PR #155.

## C07 - Manual sprint planning in Calendar

Target: v0.5. Depends on C06. Tracked by
[issue #156](https://github.com/tidus747/planacity/issues/156).

Expose the canonical sprint model in Calendar with transactional create/edit/
delete actions and explicit assignment, reassignment, and unassignment for
executable leaf work. Show scope and date diagnostics without changing dates or
rejecting irregular plans. Preserve stable identities and schema 13.

Non-goals: sprint capacity, Jira mapping, automatic distribution, velocity, and
Scrum ceremony management.

Status: completed by issue #156.

## C08 - Sprint load and capacity in Calendar

Target: v0.5. Depends on C07 and the canonical dated-capacity engine. Tracked by
[issue #179](https://github.com/tidus747/planacity/issues/179).

Project each sprint through its exact dates, explicit work assignments, and
derived whole-roster or WorkGroup participant scope. Show scheduled sprint work,
reservation-covered and ordinary demand, competing ordinary work, planning and
signed remaining capacity, unplaced demand, known-person coverage, and actionable
incomplete states. Reuse canonical source identities and calculations without a
schema change. Jira mapping and automatic distribution remain later slices.

## J01 - Additive Jira import with existing-reference anchors

Target: v0.5 usability. Safe prerequisite for v0.8 reconciliation. Tracked by
[issue #158](https://github.com/tidus747/planacity/issues/158).

Classify repeated external references as explicit omitted anchors during CSV
review. Never update them, duplicate their baseline, or infer Jira changes. Use
their stable current WorkItem IDs only to resolve hierarchy for genuinely new
rows. Store only new rows in the new snapshot and block deleted anchors or files
with no new work. Full comparison and conflict resolution remain in #139.

## J02 - Imported provenance cue in Plan

Target: v0.5 usability. Tracked by
[issue #159](https://github.com/tidus747/planacity/issues/159).

Derive an accessible, theme-aware imported-baseline cue from existing snapshots.
Use a subtle amber tint plus a non-color indicator without locking work or
implying synchronization. This remains a separate visual PR after J01.

Status: implemented by issue #159. Plan derives provenance from snapshot WorkItem
IDs, applies a light/dark amber treatment plus an import icon, and explains that
the work remains editable and unsynchronized. No schema field or lock was added.

## S01 - Define single-person assignment transitions

Target: v0.4 correction before D01. Depends on existing allocation services.
Pure policy and tests first; do not change the decoder to reject legacy plans.
Use the [assignment decision](single-person-visual-planning.md).

New leaf work accepts zero or one Allocation, including zero-hour entries.
Reject a second person through every canonical editing service. Preserve all
legacy assignments and their computed hours; expose an unresolved finding and
allow unrelated edits/repair. Containers retain existing effort-resolution rules.
Test create, reassign, unassign, duplicate IDs, zero hours, legacy multiple people,
mixed container effort, save/reopen and immutable import snapshots. The serialized
shape is unchanged; do not preallocate a schema bump. This prerequisite is not
the complete user workflow until S02/S03 are integrated.

## S02 - Explicitly resolve legacy multiple assignments

Target: v0.4. Depends on S01.
Preview consolidation to a selected existing Allocation, preserving its ID and
the exact sum of direct hours. Show deleted allocation IDs and before/after person
loads; apply atomically only on confirmation. Cancel preserves everything.
Retain estimates, dates, dependencies and imported history. Document manual
decomposition into separately assigned leaves as the collaborative alternative.
Test 60 h + 40 h -> 100 h, zero/unknown estimates, exact decimals, resulting
overload, legacy parent-effort transfer and cancellation. Show both themes.
No automatic task-splitting wizard or guessed dependency rewiring.

## S03 - One-person editing and cross-view acceptance

Target: v0.4. Depends on S01/S02.

### S03a - Canonical ownership and safe Jira roundtrip

Tracked in [#114](https://github.com/tidus747/planacity/issues/114).
Add one canonical Jira-facing assignee per WorkItem in schema 11. An Epic
assignee is its feature owner and creates no capacity demand. A Task or Subtask
with allocated hours uses the same person for assignee and its sole Allocation.
Import preserves the mapped assignee without inventing allocated hours. Export
preserves unchanged external identity and requires an explicit per-person Jira
identity for edited/new ownership. Never export a display name by assumption.
Include assignee changes in Changes and clear current ownership only with explicit
consent when deleting a roster person. Preserve all legacy Allocations.

### S03b - Compact editing and final cross-view acceptance

Replace the multi-row authoring workflow with one person selector and explicit
allocated hours for leaves; containers show a read-only aggregate team. Existing
multi-person items show every assignment and the resolution action. Apply/Cancel,
reassignment previews and keyboard access remain consistent across all editors.
Keep estimate/allocation mismatch visible; never silently synchronize hours.
When several people contribute, use separately assigned Tasks/Subtasks rather
than consolidating their hours onto one person.

Verify People groups, Overview, workload distribution, findings, hierarchy totals,
Jira baselines, backup restore, delete-person previews, and agent-guide rules.
Update user docs/screenshots and D01 assumptions. Audit every assignment entry
point, not just the Plan inspector. Include native keyboard and light/dark
evidence. v0.4 acceptance includes legacy resolution and a collaborative parent
with two singly assigned leaves, each counted once.

## V07 - WorkGroup colors and distinct Gantt work shapes

Target: v0.5. Depends on existing topic resolution and Timeline. Before V06;
does not require critical-path calculation or new persisted colors.
Status: implemented by issue #120 with its reviewable feature PR.

Implement the visual contract in the assignment decision: resolved primary-group
bar color, stable UUID palette slots, explicit neutral unknown/ambiguous states,
and Epic bracket / Task rounded / Subtask slim silhouettes plus type labels.
Selection, warnings, dependencies and future critical marks use separate layers.
Provide a named legend; color alone must never identify a group or work type.

Verify palette stability after sorting, filtering, renaming, reopening and adding
groups; include collisions, primary overrides, group deletion and legacy multiple
memberships. Test partial dates, one-day bars, resizing, keyboard focus, high-DPI
rendering and both themes. Do not change dates or drag semantics with bar shape.
Capture real contrasting-type/group examples, with selection and warning states.

## A01 - Package the versioned planning guide contract

Target: v0.5. Depends on the existing JSON codec/export workflow. No dependency
on a provider, model, graph view, or future schema field. Implement against the
actual writer schema at that time, not a hardcoded schema 8 assumption.

Use the [architecture proposal](agent-assisted-planning.md). Bundle an offline
guide, complete field reference and valid empty/representative examples. Identify
application version, schema version and guide revision. Include a copyable
provider-neutral prompt with the actual identifiers and rules for editing a copy,
preserving IDs and import snapshots, and reporting assumptions separately.

Acceptance: packaged resources work outside a checkout; examples load and
roundtrip through the canonical codec; documented fields match the writer;
unsupported versions are explained; release checks detect stale identifiers.
Review compatibility every release, updating content only when needed.
No UI, provider SDK, custom exchange format or extra schema library in this PR.

## A02 - Expose the guide through Help and About

Target: v0.5. Depends on A01. This is the smallest user-facing feature.

Add Help -> Planning with an agent and an About button opening the same offline
guide. Display the three version identifiers, Copy instructions, and Save guide.
Copying instructions must never copy planning data implicitly. Document existing
Export JSON -> edit a separate proposal -> Restore JSON -> manually review ->
Save As. Explain structural validation versus capacity/dependency feasibility
and the absence of automatic original/proposal comparison in this first slice.

Acceptance: keyboard access, readable light/dark text, clipboard contents,
export cancellation/write errors, no network dependency, and packaged install
without source files. Include real screenshots in both themes. No model launch,
account/API configuration, automatic data transfer, or project modification.

## A03 - Review external proposals and prepare planning kits

Target: later follow-up, after feedback on A02; not a v0.5 release gate.
Depends on A01/A02 and existing dependency/capacity services. Confirm UI scope
before scheduling; split review services and UI if one PR would be too large.

Compare an exported original with a candidate using the canonical decoder and
planning services. Show entity changes, protected baseline/identity changes,
dependency conflicts and advisory capacity findings. Reject invalid input or
new/worsened dependencies in this assisted workflow; never rewrite snapshots.
Detect stale active plans/candidates before acceptance. Accept only as an
unsaved document, with no partial merge or silent overwrite.

Add explicit planning-kit preparation with a contents preview, including source
snapshots. Existing files require overwrite confirmation; cancellation or failure
must not leave a kit advertised as complete. Notes remain outside project JSON.
No implicit redaction or external upload.

Acceptance: valid proposal, malformed/unknown fields, unsupported schema,
duplicate IDs, removed allocations, immutable-baseline edits, dependency cycles,
overload, stale input, cancellation, and unchanged originals on every failure.
Review valid but infeasible work without silently adjusting hours or dates.
Capture real review UI with keyboard steps; update guide claims only when shipped.
