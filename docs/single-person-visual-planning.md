# Single-person assignments and visual work identity

Date: 2026-10-07. Status: accepted implementation contract. S01 enforces the
transition policy and reports legacy conflicts; S02 adds explicit consolidation.
Neither changes the wire format. S03a adds schema 11 canonical ownership and safe
Jira CSV roundtrip; S03b and V07 are now implemented from the accepted contracts
in the [implementation queue](implementation-queue.md). This decision supersedes
the earlier multi-person-task target and never silently migrates saved work.

## One person per executable item

Allow zero or one Allocation per leaf WorkItem, including zero-hour allocations.
Zero is necessary while drafting unassigned work. One person may have many tasks.
Keep Allocation as a separate entity with its stable ID, person, work and hours;
`WorkItem.assignee_id` records ownership, not effort, and is never derived from a
display name.
Enforce the new policy in planning services, not only by hiding a UI button.

Containers have no direct capacity Allocation. An Epic or Task with children
shows the distinct people assigned to its descendant leaves as a read-only team,
separate from its canonical assignee. An Epic assignee is always a feature owner,
including before decomposition, and never consumes capacity. That summary is not
permission to assign several people to one executable item.

Jira-facing ownership is distinct from capacity hours. Schema 11 stores one
canonical assignee per work item. On an Epic, that person is the feature owner
and does not create additional capacity demand; Epic effort remains the exact
sum of its executable descendants. On a Task or Subtask, the assignee and the
single Allocation person must agree whenever allocated hours exist. Imported
assignee text remains separate source provenance for exact unchanged export.

For collaboration, split executable work: "Calibrate beam" can contain "Adjust
optics" assigned to Nefario for 16 h and "Verify beam" assigned to Bob for 8 h.
The parent shows 24 h and two contributing people without consuming another
24 h of capacity. Dependencies between these children are explicit; hierarchy
alone does not imply execution order or propagate parent relationships.

### Hours and reassignment

The existing arithmetic already counts each Allocation once. Assignment
cardinality simplifies authoring; it is not a correction to a double-counting
bug. Preserve the shared Decimal/Fraction capacity engine and its full-window
distribution policy.

Keep estimated effort and allocated hours separate. Selecting a person may offer
the known leaf estimate as a visible draft default, confirmed on Apply. Unknown
estimates require explicit allocated hours. Partial or excessive allocation
remains a visible mismatch; do not change hours automatically when estimates,
dates or people change. Zero-hour assignment does not imply positive workload.

Reassigning changes person_id on the existing Allocation, preserving ID and hours.
Preview the new person's calendar/capacity findings, then apply atomically.
Clearing a canonical assignee never silently removes an Allocation. Remove the
Allocation explicitly first, preserving the estimate. No automatic selection of
a person, calendar, or eight-hour day.

## Compatibility and resolution

Old plans remain loadable and saveable with their exact allocations and import
snapshots. A legacy multi-person item is a visible unresolved policy finding;
all of its hours still count in People, Overview and Timeline. Never retain only
the first person, hide an allocation, or divide hours implicitly.

The structural decoder keeps accepting historically valid collections. A pure
transition policy prevents creating a multi-person leaf or adding allocations
to an unresolved item. Unrelated edits and incremental repair remain possible;
date/estimate edits must not accidentally make legacy data unloadable. Existing
mixed container/leaf effort rules remain in force. This is not a new permissive
parser: existing structural/reference errors are still rejected.

The explicit resolution action previews either cancellation or consolidation
onto a selected existing allocation. Keep its ID, set its hours to the exact sum
of all direct allocations, remove the other allocations only on confirmation,
and show before/after person loads. Do not change estimates, dates, work IDs,
dependencies or historical import records. Excess/partial effort remains visible.
For example Alex 60 h + Sam 40 h becomes Alex 100 h only after confirmation,
with Sam's 40 h removed and Alex's overload recalculated.

Use that repair only when Alex should truly own all 100 h. If Alex and Sam both
contribute, consolidation would misattribute capacity and should be cancelled.
Create separately assigned Tasks or Subtasks instead; their parent Epic rolls up
the joint effort without becoming a second capacity allocation.

Splitting work into leaves is the recommended alternative when both people
really contribute. Initially use explicit normal editing; do not invent an
automatic split wizard that must guess dates, estimates or dependency semantics.
Legacy parent-effort transfer must preserve every allocation and show the same
unresolved state if its new leaf still has several people.

S01/S02 keep the existing wire representation. S03a introduces schema 11 for
`assignee_id`; schemas 1-10 load it as unset without rewriting the source file or
discarding Allocations. Application/guide revisions must describe it.
If implementation needs new persisted input, decide its migration separately.
The external-agent review validates transitions against the original; being
accepted by the legacy-compatible decoder is not proof of meeting this policy.

## Gantt identity: group color, work shape, independent status

Interpret WorkGroup coloring as bar coloring, not dependency-arrow coloring.
Use the existing primary-topic resolver shared with Overview: nearest explicit
primary group, then unambiguous inherited membership. Multiple unresolved groups
use an "Ambiguous group" neutral pattern; no group uses a distinct "Ungrouped"
neutral style. Never select the first membership or assign a rainbow to one bar.

Derive a palette slot deterministically from WorkGroup UUID using a stable digest,
not Python's process-randomized hash or visible row order. Use corresponding
light/dark palette shades. Sorting, filtering, renaming, reopening, or adding
another group must not change existing identities. Palette collisions are
possible: group names in the legend/details remain authoritative. User-picked
persisted colors and palette editing are deferred.

| Visual channel | Meaning |
| --- | --- |
| Fill color and group label | Resolved primary WorkGroup |
| Epic bracket silhouette with end caps | Epic type, including an executable leaf Epic |
| Rounded rectangle and Task label/icon | Task type |
| Slim rectangle and Subtask label/icon | Subtask type |
| Separate child-count/summary marker | Work has children, independently of its type |
| Focus/selection outline | Current keyboard or pointer selection |
| Warning icon and text | Invalid or incomplete planning inputs |
| Red critical connector and outer mark | Critical path, when V05/V06 are implemented |

Keep existing canonical dates and permitted drag/keyboard behavior. A different
shape does not roll up dates, create milestones, or make a container bar a
calculated duration. Partial-date/open-ended indicators, short bars and resize
handles must remain legible and reachable. Do not encode a milestone as a diamond
until the first-class Milestone feature exists.

Dependency edges retain their relationship/validation styles. Critical-path
marks overlay group identity without replacing the fill. Selection, warnings,
criticality and work type must coexist without relying on red versus green or
color alone. Priority uses its own text/icon; it does not set the bar color.
Named, hatched absence overlays and reservation lanes remain visually distinct.

## Cross-feature consistency review

| Existing or planned feature | Result of this decision |
| --- | --- |
| Hierarchy effort | Sum leaves once; show the aggregate team on parents |
| Capacity, reservations, calendars | Keep the engine; reassignment changes whose demand/calendar is used |
| People WorkGroups | Still derived from positive allocations; one person can work across many groups |
| Overview topics | Same primary-topic resolver as Gantt, no multi-group double counting |
| Inspector | One person selector and allocated hours on leaves; team summary on parents |
| Jira CSV and baselines | Preserve source provenance; S03a adds one canonical assignee, with Epic assignee as feature owner and leaf assignee aligned with its Allocation |
| Descriptions, labels, priority | Independent metadata; priority does not determine criticality or bar color |
| Dependency graph | One assignee on a normal leaf card, aggregate names on a container, explicit legacy warnings |
| Critical path | Dependency/duration calculation unchanged; resource feasibility remains separate |
| Moon Heist demo | Replace shared leaf tasks with separately assigned subtasks |
| Agent guidance | Teach one allocation per leaf, preserve legacy data and explain unresolved assignments |

The corrections belong before D01 and v0.4 acceptance so the new demonstration
teaches the intended model. V07 belongs to v0.5 and can ship without critical-path
analysis. Neither requires an embedded agent, a new UI framework or a backend.
