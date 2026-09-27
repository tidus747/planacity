"""Application document state; failed I/O leaves the current session intact."""

from dataclasses import dataclass
from pathlib import Path

from planacity.domain import ProgramPlan
from planacity.persistence.project import load_project, restore_backup, save_project


@dataclass
class Document:
    plan: ProgramPlan | None = None
    path: Path | None = None
    saved_plan: ProgramPlan | None = None

    @property
    def dirty(self) -> bool:
        return self.plan is not None and self.plan != self.saved_plan

    def new(self, plan: ProgramPlan) -> None:
        self.plan, self.path, self.saved_plan = plan, None, None

    def open(self, path: Path) -> None:
        plan = load_project(path)
        self.plan, self.path, self.saved_plan = plan, path, plan

    def restore(self, path: Path) -> None:
        self.new(restore_backup(path))

    def save(self, path: Path | None = None) -> None:
        target = path if path is not None else self.path
        if self.plan is None or target is None:
            raise ValueError("Create a plan and choose a project path before saving.")
        save_project(self.plan, target)
        self.path, self.saved_plan = target, self.plan
