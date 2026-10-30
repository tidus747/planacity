"""Fail a build when the planning-guide contract is absent from distributions."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

RESOURCES = (
    "instructions.md",
    "empty-plan.json",
    "representative-plan.json",
)


def _one(directory: Path, pattern: str) -> Path:
    matches = tuple(directory.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"Expected one {pattern} in {directory}, found {len(matches)}.")
    return matches[0]


def _missing(names: set[str], marker: str) -> tuple[str, ...]:
    return tuple(
        resource
        for resource in RESOURCES
        if not any(name.endswith(f"{marker}/{resource}") for name in names)
    )


def check(directory: Path) -> None:
    wheel = _one(directory, "*.whl")
    source = _one(directory, "*.tar.gz")
    with zipfile.ZipFile(wheel) as archive:
        wheel_missing = _missing(set(archive.namelist()), "resources/planning-guide")
    with tarfile.open(source, "r:gz") as archive:
        source_missing = _missing(
            {member.name for member in archive.getmembers()},
            "src/planacity/resources/planning-guide",
        )
    if wheel_missing or source_missing:
        raise ValueError(
            "Planning-guide resources missing from distributions: "
            f"wheel={wheel_missing}, source={source_missing}."
        )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: check_planning_guide_distribution.py DIST_DIRECTORY")
    check(Path(sys.argv[1]))
    print("Planning-guide resources are present in the wheel and source distribution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
