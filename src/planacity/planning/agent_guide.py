"""Version-matched offline contract for agent-assisted planning."""

from dataclasses import dataclass
from importlib.metadata import version
from importlib.resources import files

from planacity.persistence.codec import SCHEMA_VERSION

GUIDE_REVISION = "1"
_RESOURCE_DIRECTORY = ("resources", "planning-guide")


@dataclass(frozen=True)
class PlanningGuide:
    """A complete guide contract loaded without a checkout or network access."""

    application_version: str
    schema_version: int
    guide_revision: str
    instructions: str
    empty_example: str
    representative_example: str


def _resource_text(filename: str) -> str:
    resource = files("planacity")
    for part in _RESOURCE_DIRECTORY:
        resource = resource.joinpath(part)
    return resource.joinpath(filename).read_text(encoding="utf-8")


def load_planning_guide() -> PlanningGuide:
    """Load the packaged guide and compose its canonical version header."""
    application_version = version("planacity")
    body = _resource_text("instructions.md").strip()
    header = (
        "# Planacity planning guide\n\n"
        f"- Application version: {application_version}\n"
        f"- JSON schema version: {SCHEMA_VERSION}\n"
        f"- Guide revision: {GUIDE_REVISION}\n\n"
    )
    return PlanningGuide(
        application_version=application_version,
        schema_version=SCHEMA_VERSION,
        guide_revision=GUIDE_REVISION,
        instructions=header + body + "\n",
        empty_example=_resource_text("empty-plan.json"),
        representative_example=_resource_text("representative-plan.json"),
    )
