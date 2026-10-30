"""The packaged planning guide must stay aligned with the canonical writer."""

import json
import re

from planacity.persistence.codec import FORMAT, SCHEMA_VERSION, dumps, loads
from planacity.planning.agent_guide import GUIDE_REVISION, load_planning_guide


def _documented_fields(text: str, heading: str) -> set[str]:
    section = text.split(f"### {heading}\n", 1)[1].split("\n### ", 1)[0]
    statement = re.search(r"Field set: (.*?)\.\n", section, re.DOTALL)
    assert statement is not None
    return set(re.findall(r"`([^`]+)`", statement.group(1)))


def test_guide_uses_canonical_versions_and_contains_no_unresolved_placeholders():
    guide = load_planning_guide()

    assert guide.application_version
    assert guide.schema_version == SCHEMA_VERSION == 14
    assert guide.guide_revision == GUIDE_REVISION == "1"
    assert f"Application version: {guide.application_version}" in guide.instructions
    assert f"JSON schema version: {SCHEMA_VERSION}" in guide.instructions
    assert f"Guide revision: {GUIDE_REVISION}" in guide.instructions
    assert "{{" not in guide.instructions
    assert "}}" not in guide.instructions
    assert "C:\\Users" not in guide.instructions
    assert "/home/" not in guide.instructions


def test_packaged_examples_use_the_current_schema_and_roundtrip():
    guide = load_planning_guide()

    for text in (guide.empty_example, guide.representative_example):
        raw = json.loads(text)
        assert raw["format"] == FORMAT
        assert raw["schema_version"] == SCHEMA_VERSION
        plan = loads(text)
        assert loads(dumps(plan)) == plan


def test_representative_example_exercises_every_persisted_collection():
    plan = loads(load_planning_guide().representative_example)

    for field in (
        "work_items",
        "people",
        "work_groups",
        "relationships",
        "imports",
        "work_calendars",
        "person_calendars",
        "availability_events",
        "calendar_events",
        "reservation_rules",
        "allocations",
        "reservation_coverages",
        "sprints",
        "sprint_assignments",
    ):
        assert getattr(plan, field), field


def test_documented_field_sets_match_every_current_writer_object():
    guide = load_planning_guide()
    root = json.loads(guide.representative_example)
    plan = root["plan"]
    snapshot = plan["imports"][0]
    objects = {
        "ProgramPlan": plan,
        "PlanningHorizon and period values": plan["horizon"],
        "WorkItem": plan["work_items"][0],
        "Person": plan["people"][0],
        "WorkGroup": plan["work_groups"][0],
        "Relationship": plan["relationships"][0],
        "ImportSnapshot": snapshot,
        "ImportedWork": snapshot["records"][0],
        "WorkCalendar": plan["work_calendars"][0],
        "PersonCalendar": plan["person_calendars"][0],
        "AvailabilityEvent": plan["availability_events"][0],
        "CalendarEvent": plan["calendar_events"][0],
        "ReservationRule": plan["reservation_rules"][0],
        "EstimatePreferences": plan["estimate_preferences"],
        "Allocation": plan["allocations"][0],
        "ReservationCoverage": plan["reservation_coverages"][0],
        "Sprint": plan["sprints"][0],
        "SprintAssignment": plan["sprint_assignments"][0],
    }

    assert _documented_fields(guide.instructions, "Backup root") == set(root)
    for heading, value in objects.items():
        assert _documented_fields(guide.instructions, heading) == set(value), heading
