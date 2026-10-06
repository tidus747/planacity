# Implementation queue and review briefs

Planning revision: 2026-10-04. These are future implementation briefs, not
completed features. Read the [roadmap](roadmap.md) and
[calculation decisions](planning-decisions.md) together with this queue.
GitHub owns live status. Do not duplicate an existing issue or close it merely
because its specification is written here.

## Start the next session

1. Check main, the working tree, open issues, and pending PRs. R01-R09 are
   merged; R10 is tracked in issue #100. Do not merge without maintainer approval.
2. Finish or review R10 before selecting P01, its canonical priority slice.
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
| v0.4 finishing slices | R10 -> P01 -> P02 -> D01 | People groups, priorities, CSV mapping, a memorable example |
| v0.5 visual planning | V01 -> V02 -> V03 -> V04 -> V05 -> V06 | Team visibility, dependency cards, then critical-path analysis |

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
- Verify multi-person tasks, multiple groups, duplicate names, group deletion,
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

Target: v0.4. Depends on R03-R10, P01, and P02.

Create the additive example and walkthrough from the
[scenario specification](moon-heist-example.md). Do not replace Aurora's legacy
migration fixture. Use the actual schema at implementation time.

Acceptance: deterministic IDs/dates and expected totals; valid dependencies;
multi-person work; work groups; descriptions; priorities; reservations; an
absence; save/reopen and a small CSV roundtrip. Keep a coherent initial plan and
separate documented exercises that introduce missing data or overload.
Capture real Overview, Plan, People, and Timeline images when available.
V04/V06 extend this same example later, without pretending those features exist.

## V04 - Visual dependency neighbourhood (existing scope)

Target: v0.5. Depends on R02, R03, and R08.

Keep the existing roadmap scope: selected item, immediate predecessors and
successors, dates, assigned people, findings, and keyboard/text navigation.
Show at most 30 cards and an explicit omitted-items list. Test cycles, partial
dates, long titles, multiple allocations, and hidden endpoints. Use Qt directly.
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

Target: v0.5. Depends on V04 and V05.

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
