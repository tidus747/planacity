# Planning consistency and visibility decisions

Revised: 2026-10-07. Status: active implementation contract.
Dependency guards, hierarchy effort, dated capacity, reusable findings, People
breakdowns, persisted work context, compact Overview analysis, and derived People
WorkGroup associations, canonical work priority, and explicit Jira CSV priority
mapping are implemented. Work context introduced schema 8, priority schema 9,
and preserved Jira source-priority text schema 10; the transactional Plan
inspector, Overview analysis, and People associations require no further schema
change.
Later presentation sections remain future behavior.
See the [roadmap](roadmap.md) for order and acceptance.

## Assignment-policy revision (2026-10-07)

The [single-person and visual planning decision](single-person-visual-planning.md)
supersedes multi-person assignment as the target editing model. S01 limits new
executable leaves to zero or one Allocation while preserving every legacy entry,
hour, and calculation. S02 explicitly consolidates a legacy conflict onto one
selected existing Allocation after a before/after preview. S03 will add the final
one-person editor, Jira-aligned assignees, and aggregate container teams. An Epic
assignee is a feature owner without additional capacity demand; a leaf assignee
must match its sole Allocation when hours exist. Existing calculation and
preservation rules below still apply to every stored allocation. V07 adds
group-colored bars and type-specific shapes independently.

## 1. One source of calculation truth

Keep immutable ProgramPlan inputs and pure planning services. Plan, People,
Timeline, and Overview consume the same computed results for the same date
range. Qt presents values and actions; it must not calculate capacity or decide
dependency validity. No new framework or background service is needed.

Persist input values, stable identities, and explicit user choices. Do not persist
cached charts, rolled-up totals, generated duty occurrences, or findings. Preserve
exact Decimal input hours and exact rational intermediate shares. Round only for
display; totals must conserve input hours before rounding.

## 2. Separate effort, allocations, and elapsed dates

- Estimate: planned effort needed to complete the work.
- Allocation: hours of that effort assigned to one person.
- Start/end: inclusive calendar dates within which the work is planned.
- Capacity: hours available from a person's calendar after entered reductions.

A shorter Gantt bar does not reduce effort. A larger estimate does not move dates.
Changing a reference calendar changes day/week display equivalents, not a
person's capacity. Always keep Hours available without a conversion calendar.

## 3. Hierarchy rollups and legacy data

Leaf work holds editable effort. A container's effective estimate sums the leaf
work below it, once. Apply this recursively to Epics/Tasks/Subtasks. If any leaf
has an unknown estimate, present a known subtotal and missing count, not a false
complete total. A known zero remains different from missing effort.

Example: children 60 h and 40 h produce 100 h; children 60 h and unknown produce
"60 h known; 1 estimate missing". Do not add an Epic's historical 150 h reference
estimate on top of its 100 h of leaf effort. Retain that 150 h in storage and show
it separately as entered/imported reference effort, never as consumed capacity.

Roll up assigned hours separately by unique allocation ID. Existing schema 7
plans may allocate both a parent and its children. Keep every such allocation
visible and counted in capacity, flag mixed-level effort, and mark the relevant
summary incomplete until resolved. Never silently discard or copy assignments.

For new edits, a container receives effort through its leaves. Before turning an
allocated leaf into a container, offer an explicit preview to move its direct
effort/allocations into a new leaf or cancel. Existing mixed-level plans need the
same resolution action; transferring an allocation preserves its ID and hours,
and only explicitly changes its work reference. Do not automatically subtract
child estimates from parent estimates. Dates, groups, and dependencies do not
move as a side effect of effort resolution.

Default Jira exports keep their explicit stored-estimate convention. Preview must
identify entered/reference values versus computed container totals. Exporting
rollups later requires an explicit mapping option, never silently writing derived
values into imported baselines or current stored estimates.

## 4. Capacity calculation and time distribution

For each person/date, calculate from configured inputs:

    Nominal calendar hours
    - Recorded unavailability
    - Capacity-affecting program events (once implemented)
    = Available hours before duties
    - Recurring reservations
    = Planning capacity
    - Scheduled allocated work
    = Remaining capacity

v0.4 uses calendars, recorded availability, and saved reservations. Program-event
deductions join in v0.5; UI copy states which inputs are included. Existing
availability overlap handling (strongest fraction) and reservation proration
(equal shares over eligible days in complete anchored periods) remain unchanged.

The initial allocation schedule uses its WorkItem's complete start/end window;
it does not inherit dates from a parent or silently use the visible horizon.
Within that window, distribute each allocation proportionally to positive daily
planning capacity after reservations. This is a documented planning assumption,
not a measured schedule. Each person's distribution uses their own calendar.

For allocation H and daily weights w = max(planning capacity, 0), the daily share
is H * w / sum(w). Calculate over the full window first, then clip/aggregate into
days, weeks, or the selected range. Other allocations do not alter those weights:
sum their demand afterwards so concurrent work produces overload rather than
quietly moving work elsewhere. Dates and stored hours never change.

If all weights are zero, retain the hours as demand that cannot be scheduled in
that window and report it. Missing calendars or incomplete dates also produce
unplaced demand, with the specific reason. Do not manufacture an allocation
schedule or a remaining-capacity percentage. For a fully dated zero-capacity
window, show that window; for undated work, show plan-wide unplaced hours without
inventing a share inside the selected interval.

Reservations with no eligible days retain their requested hours and an unresolved
occurrence finding. Do not read a null preview deduction as a zero-hour duty.
Retain negative planning/remaining capacity when duties or work exceed it.
Impractically large query windows return an actionable incomplete result, not
partial totals presented as complete; chunking/caching is an implementation detail.

Example: 80 nominal hours - 8 unavailable - 6 meetings - 10 front office leaves
56 planning hours. 48 allocated hours leaves 8 h; 64 leaves -8 h. Two overlapping
tasks must be summed per day even if each fits its whole window on its own.
Non-overlapping tasks are not falsely reported as simultaneous overload.

## 5. Findings, data coverage, and edit boundaries

Capacity findings are advisory, not hard limits on saving a plan. A user must be
able to capture an infeasible proposal and then repair it. Invalid types,
references, negative input hours, and reversed date ranges remain hard errors.

Compute findings with rule key, severity, affected identities/interval, message,
and suggested action. Missing calendar, missing dates/estimate, unassigned work,
estimate/allocation mismatch, unschedulable demand, mixed-level effort, and
overload remain distinct. Zero planning capacity is not an unknown calendar.

Every overview names its date range, input coverage, and unresolved demand.
Known per-person values may still be shown when another person is incomplete,
but a partial team subtotal is not labelled total free capacity or a healthy
plan. Unallocated estimated work means positive headroom is provisional; unknown
estimates prevent a claim that all required work fits.

Work/topic filters alter what is highlighted, not the competing work used to
evaluate a person's load. State when other work is hidden. Count people by UUID,
not row occurrences or names. Show positive work-allocation coverage separately
from people with reservations only. "3 of 5 people have planned work" is a review
notice, not an error or productivity score; zero-capacity/absent people may be
intentionally unassigned. Visible-filter counts are separate from full-plan counts.

## 6. Dependencies are finish-to-start constraints

Normalize `A depends_on B` to B -> A and `A blocks B` to A -> B. With inclusive
day dates, predecessor end must be strictly earlier than successor start.
Same-day handoffs, lag, other dependency types, and automatic scheduling are
future work. Hierarchy and `related_to` create no scheduling constraint.

Use one shared validator for relationship edits, Plan dates, inspector dates,
Timeline keyboard dates, and drag proposals. A new conflict rejects the edit with
affected work and permitted boundary; invalid drag release leaves original dates.
Check incoming and outgoing edges, including endpoints hidden by filters.

Old/imported inconsistent plans remain loadable. For a fully dated edge, conflict
magnitude is max(0, predecessor end ordinal - successor start ordinal + 1).
An edit may reduce or preserve an existing conflict, but must not introduce or
increase one on any affected edge. Unrelated existing conflicts do not block
repair. Clearing a date is allowed but changes that edge to unevaluated, with a
visible finding; the UI must not report it as resolved. New cycles are rejected;
legacy/imported cycles remain visible findings, never deleted automatically.

No auto-clamping to a date, cascading moves, or silent changes to dependency type.
Any future schedule repair wizard must preview every affected item separately.

## 7. Topics and labels serve different purposes

Reuse WorkGroup as the named planning topic. Add an optional primary WorkGroup
reference on work for additive reporting; inherit the nearest explicit choice
down the hierarchy. This supports standalone Tasks and deliberate child overrides.
Preserve existing multi-group Epic membership as organizational/filter context.
Effective group filters include inherited memberships and the resolved primary
group, without copying membership lists into every child.

For legacy work without an explicit primary choice, exactly one inherited group
can resolve the reporting topic without a stored rewrite. No group maps to
Ungrouped; multiple inherited groups map to Ambiguous group until the user chooses.
An explicit primary selection wins. Group deletion previews these references.

Every allocated hour is attributed to exactly one resolved topic or exception
bucket. Never sum multi-valued label memberships as slices of a whole. Estimated
topic effort uses leaves only and is a different measure from allocated hours.
Example: 60 h in Alpha and 40 h ungrouped total 100 h even if the Alpha task also
has labels `firmware` and `customer-a`.

Labels are optional lightweight text metadata alongside a plain-text description.
No rich-text runtime, dynamic custom-field engine, or full Jira field model.
Jira CSV may later map labels and selected WorkGroups explicitly; names are not
automatically converted into Jira-safe tags and source labels are not overwritten.

## 8. Visual presentation without extra infrastructure

Overview gets one collapsible analysis area, not a configurable dashboard. Use
horizontal bars and a readable table with the same values. Negative headroom and
missing data require distinct annotations, not clipped bars or colour alone.

Timeline keeps Plan mode and gains Team mode, with independent controls for
unavailability and reservations. Absences use named hatched bars with a legend
and partial-day share. Reservations are period budgets labelled with rule name
and hours; drawing them does not invent appointment times. Keep them in separate
lanes so they do not obscure or duplicate editable task bars. Visibility settings
are local view preferences; saving them must not modify planning data.

Dependency details gain a three-column neighbourhood graph: predecessors,
selected item, successors. Include dates, a people icon plus names/count, and
warnings. Start with one hop and at most 30 cards, stable ordering, an explicit
omitted-node count/list, and click-to-recenter. Keep the text/list alternative and
keyboard selection; cycles and incomplete dates must not break layout.

Use the already installed Qt stack. Qt's
[QGraphicsView](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html)
provides scene interaction; its
[QPainter](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QPainter.html)
supports drawing the simple cards, arrows, and bars. This is a design choice
based on those capabilities, not a need for a new graph-layout dependency.
Do not add Graphviz executables, Mermaid/browser rendering, or a web backend.

## 9. People work groups are derived associations

R10 derives a person's associations from positive allocations to work, using
R07's effective group context. Do not persist a parallel membership list on
Person. Show one roster row per person with all associated group names. Group
filters and sorting organize that roster without duplicating capacity totals.
People without allocations remain visible under an explicit no-assigned-work
state. Zero-hour allocations do not imply active work in a group.

Association labels describe the whole plan. Period hours use R04 and are labelled
with the interval; undated demand remains separately visible. A person can belong
to several context groups, but additive group-hour reporting uses the single
primary topic or Ungrouped/Ambiguous bucket. Filtered work never becomes the
entire competing workload used to calculate that person's remaining capacity.

## 10. Priority is independent of scheduling criticality

Use optional canonical levels Highest, High, Medium, Low, Lowest, in that order.
Unset is a separate empty state, not an alias for Medium. No inheritance or
automatic assignment when an Epic gains children. Priority edits change neither
dates nor effort nor dependencies. Labels/icons must work without color alone.

Jira ships these five defaults but allows administrators to change priorities
and schemes. See [Atlassian's priority configuration documentation](https://support.atlassian.com/jira-cloud-administration/docs/configure-priorities-for-projects/).
P02 maps CSV values explicitly, preserving source values and baselines. Exact
default-name matches are reviewable suggestions, custom values may remain visibly
unresolved/Unset, and no numeric ID is treated as a universal order. Unchanged
work exports its original nonblank label; edits and new work use explicit target
labels. P01 owns canonical storage/editing; P02 owns previewed import/export
mappings and the schema 10 source-text copy.

## 11. Initial critical-path analysis contract

V05 implements a deliberately bounded, pure dependency/duration analysis.
V06 presents it as "Critical path (elapsed days)" with assumptions visible.
This is a design choice for the first release, not a resource-feasible schedule
or an analysis of working-day calendars. The
[PMI CPM calculation explanation](https://www.pmi.org/learning/library/critical-path-method-calculations-scheduling-8040)
describes early/late dates and total float. The rules below define Planacity's
initial scope; they must be tested independently of Qt.

### Inputs and coverage

- Scope is all leaf work in the ProgramPlan, independent of horizon clipping,
  filters, grouping, and priority. A leaf Epic is still work; a parent with
  children is a summary and is not counted as a second activity.
- Each leaf needs both dates. Duration is end ordinal - start ordinal + 1,
  measured in elapsed days. A one-day task has duration 1. Hours and person
  calendars do not define this duration; weekends inside the bar count.
- Normalize/deduplicate finish-to-start links using R02. Ignore `related_to`.
  Parent/child structure adds no edge. A dependency involving a container is
  unsupported initially: report it, do not silently expand or discard it.
- Missing dates, cycles, invalid references, or existing date conflicts prevent
  a whole-plan result. Return affected IDs and reasons, not a best-looking
  partial critical path. Empty work reports no analysis. Retain the ordinary
  Timeline and dependency findings even when criticality cannot be evaluated.

### Calculation and interpretation

Use a synthetic source connected to every root and sink connected from every
terminal leaf. They are internal calculation nodes, not persisted milestones.
Take offset zero at the earliest entered leaf start. Start/end offsets below use
exclusive finish boundaries internally; stored dates stay inclusive.

    ES(task) = max(EF(predecessors)), or 0 for roots
    EF(task) = ES(task) + duration(task)
    finish = max(EF(all tasks))
    LF(task) = min(LS(successors)), or finish for terminals
    LS(task) = LF(task) - duration(task)
    total_float(task) = LS(task) - ES(task)

All zero-total-float activities are critical. A critical edge must also be tight:
EF(predecessor) == ES(successor). Return all tied longest paths via their node
and edge sets; do not enumerate exponentially many full paths. Disconnected
shorter branches receive float against the common calculated finish.

Entered start dates establish durations and the common origin, not individual
release constraints. Gaps between entered bars are not modeled as dependencies
or lag. Explain that calculated early/late dates are hypothetical offsets from
that origin; float is analytical flexibility, not permission to drag past R02
constraints or a promise about current scheduled gaps. The overlay marks the
calculated critical chain on the existing bars without moving any of them.
No calendar levelling, deadline constraints, lag, or actual-time tracking here.

Example: A lasts 2 days; B lasts 3 and C lasts 1, both after A; D lasts 2 after
both B and C. Finish is offset 7. A/B/D have zero float, C has 2 days float.
Only A -> B -> D is critical. If C also lasts 3, both branches are critical.
Making C Highest priority changes neither result. Scheduled gaps may make the
entered completion later than this earliest dependency-only completion.

### Presentation

Use red critical connectors plus distinctive line treatment, a legend and
textual critical/float details. Dependency conflicts use their existing warning
style and message, not the same unexplained red line. Show every tied chain.
Keep a keyboard-accessible list and graph alternative; verify both themes.
Filters hide presentation only: report hidden critical nodes, never calculate
a different path from visible rows. Invalidated or incomplete analysis clears
the overlay and explains why. No cached critical state in project files.

## Consequences

Computed rollups and dated allocations deliberately change today's independent
parent/child summaries; they require migration previews and cross-view tests.
The first daily work profile is an explicit approximation, not automatic resource
levelling. Keep that policy visible when dates or calendars change its profile.

This sequence brings useful analysis forward while deferring generic dashboards,
advanced scheduling, and HR integration. Its acceptance criterion is explainable,
consistent planning information, not reaching a target number of charts or issues.
