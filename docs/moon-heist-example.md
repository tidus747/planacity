# Operation Moon Heist: demonstration specification

Status: planned D01 dataset, not an example file available to open yet.
This is a playful fictional plan inspired by Gru and the minions: prepare a
shrink ray, build a banana-powered spacecraft, capture the Moon, and bring it
home for a triumphant demonstration. Write original scenario text; use real
Planacity screenshots rather than film stills or mock application images.

## Cast and structure

Gru is the program sponsor in the plan description. The allocatable roster is
Dr. Nefario, Kevin, Stuart, Bob, and Dave. Give each a calendar; do not treat a
person's name or fictional role as a productivity rating.

| WorkGroup / Epic | Example leaf work | People |
| --- | --- | --- |
| Shrink technology / Build the shrink ray | Design lens, calibrate beam, test on a toy moon | Dr. Nefario, Bob |
| Spacecraft / Prepare the banana rocket | Assemble propulsion, integrate guidance, rehearse launch | Kevin, Stuart |
| Lunar operations / Capture and return | Confirm flight plan, fly to the Moon, shrink and retrieve, return home | Kevin, Bob, Dave |
| Mission support / Prepare the secret base | Stock bananas, prepare hangar, document the demonstration | Stuart, Dave |

Use 4 Epics and approximately 12-16 leaf tasks. Include one Task with two
Subtasks so rollups are visible. Container estimates are derived, not allocated
again. At least one task has two people sharing its entered estimate; at least
one person works across WorkGroups. All priorities and descriptions are visible
only after their corresponding fields are implemented.

## Deterministic planning inputs

Use the fixed horizon 2027-01-04 through 2027-02-12, not today's date. Choose
stable IDs so screenshots, CSV references, and validation results are repeatable.

- Standard calendar: Monday-Friday, 8 h/day. Bob: Monday-Friday, 6 h/day.
- Weekly mission briefing: 2 h/person per full Monday-anchored weekly period.
- Kevin's front office duty: 4 h/week, separately named and visible.
- Stuart unavailable on 2027-01-18; store only unavailable capacity, not HR detail.
- Example shared task: calibrate beam, 24 h split Nefario 16 h / Bob 8 h.
- Set every baseline leaf estimate equal to the sum of its positive allocations.
  Schedule dependent leaves with predecessor end strictly before successor start.
- Include independent support work and parallel prerequisites converging on
  launch. Do not encode hierarchy or `related_to` as scheduling edges.

These are design inputs. The implementation must calculate and record exact
per-person/group/plan totals and daily feasibility before calling the dataset
valid. Do not guess a green capacity result from horizon totals alone.
For a reproducible check, one full standard week has 40 nominal hours and 38
planning hours after briefing; Kevin has 34 after both duties. Bob has 28.
These checks assume no absence in that week.

## Guided review exercises

Start with complete calendars, estimates, allocations, feasible daily demand,
and valid dependencies. A new user should understand the plan before repairing
it. Perform each exercise in a restored copy, with expected findings in the guide.

1. Explain where Kevin's time goes: two work groups, briefing, front office,
   allocated work, and remaining capacity, all reconciling to People/Overview.
2. Add concurrent assigned hours to create a known overload. Document the precise
   input change, affected interval, and expected deficit after calculation.
3. Clear an estimate/calendar in separate copies to demonstrate unknown inputs
   without presenting unknown capacity as zero or free time.
4. Attempt to move launch before a prerequisite finishes. The date guard rejects
   it without changing the saved dates; a permitted move keeps effort constant.
5. Edit a description and priority, save/reopen, then preview a Jira CSV export
   without altering the imported reference snapshot.
6. After V04/V06 ship, inspect the fork/join neighbourhood and critical overlay.
   Document why high priority and criticality can differ.

## Packaging and scope

Add `moon-heist.planacity.json`, a small matching Jira-style CSV, and a walkthrough
when D01 is implemented. Open the backup as an unsaved copy. Validate restoring,
saving, reopening, fixture totals, and CSV provenance without relying on today.
Keep `aurora.planacity.json` and its legacy-schema tests unchanged.

Future first-class milestones and deliveries belong to v0.6. Until then, describe
mission outcomes in prose; do not fabricate zero-duration work to impersonate
those entities. Website screenshots follow working functionality, with light and
dark examples where useful. This specification adds no application assets.
