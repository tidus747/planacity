"""Small text presentation helpers for canonical planning findings."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QStyle, QWidget

from planacity.planning.findings import PlanningFinding


def finding_note(findings: tuple[PlanningFinding, ...]) -> str:
    if not findings:
        return ""
    titles = tuple(dict.fromkeys(finding.title for finding in findings))
    if len(findings) == 1:
        return titles[0]
    preview = ", ".join(titles[:2])
    if len(titles) > 2:
        preview += ", ..."
    return f"{len(findings)} findings: {preview}"


def finding_details(findings: tuple[PlanningFinding, ...]) -> str:
    if not findings:
        return "Planning findings: none."
    lines = [f"Planning findings ({len(findings)}):"]
    for finding in findings:
        lines.append(f"- {finding.title}: {finding.explanation} Next: {finding.suggested_action}")
    return "\n".join(lines)


class FindingView(QWidget):
    """Accessible warning icon and text for one calculated findings snapshot."""

    def __init__(self, accessible_name: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.icon = QLabel()
        self.icon.setAccessibleName(f"{accessible_name} icon")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.icon.setPixmap(
            QApplication.style()
            .standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
            .pixmap(20, 20)
        )
        self.message = QLabel()
        self.message.setAccessibleName(accessible_name)
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.icon)
        layout.addWidget(self.message, 1)

    def set_findings(self, findings: tuple[PlanningFinding, ...]) -> None:
        self.icon.setVisible(bool(findings))
        self.message.setText(finding_details(findings))

    def text(self) -> str:
        return self.message.text()
