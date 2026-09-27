"""One shared document and change signal for every desktop view."""

from PySide6.QtCore import QObject, Signal

from planacity.document import Document
from planacity.domain import ProgramPlan


class Session(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.document = Document()

    def apply(self, plan: ProgramPlan) -> None:
        if plan != self.document.plan:
            self.document.plan = plan
            self.changed.emit()
