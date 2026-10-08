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

Keep the existing roadmap scope: selected item, immediate predecessors and
successors, dates, assigned people, findings, and keyboard/text navigation.
Show at most 30 cards and an explicit omitted-items list. Test cycles, partial
dates, long titles, legacy multiple allocations, aggregate parent teams, and
hidden endpoints. Use Qt directly.
Capture a branching graph in both themes. No full graph editor or CPM required.

## V05 - Critical-path analysis service

Target: v0.5. Depends on R02 and R03. Pure service and tests; no UI in this PR.

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
Replace the multi-row authoring workflow with one person selector and explicit
allocated hours for leaves; containers show a read-only aggregate team. Existing
multi-person items show every assignment and the resolution action. Apply/Cancel,
reassignment previews and keyboard access remain consistent across all editors.
Keep estimate/allocation mismatch visible; never silently synchronize hours.

Add one canonical Jira-facing assignee per WorkItem. An Epic assignee is its
feature owner and creates no capacity demand; its displayed effort/team still
rolls up executable descendants. A Task or Subtask with allocated hours uses the
same person for assignee and its sole Allocation. Import preserves the mapped
assignee without inventing allocated hours. Export preserves unchanged external
identity and explicitly previews the local assignee used for edited/new work.
When several people contribute, use separately assigned Tasks/Subtasks rather
than consolidating their hours onto one person. Define migration and external
person mapping explicitly before implementation; never export a display name as
a Jira account identifier by assumption.

Verify People groups, Overview, workload distribution, findings, hierarchy totals,
Jira baselines, backup restore, delete-person previews, and agent-guide rules.
Update user docs/screenshots and D01 assumptions. Audit every assignment entry
point, not just the Plan inspector. Include native keyboard and light/dark
evidence. v0.4 acceptance includes legacy resolution and a collaborative parent
with two singly assigned leaves, each counted once.

## V07 - WorkGroup colors and distinct Gantt work shapes

Target: v0.5. Depends on existing topic resolution and Timeline. Before V06;
does not require critical-path calculation or new persisted colors.

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
