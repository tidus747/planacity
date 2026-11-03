"""Offline planning-guide and About dialogs with no access to plan data."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from planacity.planning.agent_guide import load_planning_guide


class PlanningGuideDialog(QDialog):
    """Display and export the packaged instructions without touching a plan."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.guide = load_planning_guide()
        self.setObjectName("planningGuideDialog")
        self.setWindowTitle("Planning with an agent")
        self.setModal(True)
        self.resize(900, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        title = QLabel("Planning with an agent")
        title.setProperty("role", "title")
        layout.addWidget(title)
        summary = QLabel(
            "Use the version-matched offline contract with an external assistant. "
            "Planacity does not launch a model, use the network, or include your plan "
            "when you copy or save these instructions."
        )
        summary.setWordWrap(True)
        summary.setAccessibleName("Planning guide privacy summary")
        layout.addWidget(summary)

        identifiers = QHBoxLayout()
        identifiers.setSpacing(8)
        self.identifier_labels: dict[str, QLabel] = {}
        for key, value in (
            ("Application", self.guide.application_version),
            ("JSON schema", str(self.guide.schema_version)),
            ("Guide revision", self.guide.guide_revision),
        ):
            identifier = QLabel(f"{key}: {value}")
            identifier.setProperty("role", "badge")
            identifier.setAccessibleName(f"{key} version {value}")
            self.identifier_labels[key] = identifier
            identifiers.addWidget(identifier)
        identifiers.addStretch()
        layout.addLayout(identifiers)

        self.workflow = QLabel(
            "Current workflow: Export JSON -> edit a separate proposal -> Restore JSON -> "
            "manually review -> Save As. Structural validation does not prove that capacity "
            "or dependencies are feasible, and automatic original/proposal comparison is not "
            "available yet."
        )
        self.workflow.setWordWrap(True)
        self.workflow.setProperty("role", "muted")
        self.workflow.setAccessibleName("Current assisted planning workflow")
        layout.addWidget(self.workflow)

        self.instructions = QPlainTextEdit()
        self.instructions.setObjectName("planningGuideInstructions")
        self.instructions.setAccessibleName("Planning guide instructions")
        self.instructions.setReadOnly(True)
        self.instructions.setPlainText(self.guide.instructions)
        layout.addWidget(self.instructions, 1)

        self.status = QLabel(
            "Copying or saving includes these instructions only. No planning data is included."
        )
        self.status.setProperty("role", "muted")
        self.status.setAccessibleName("Planning guide action status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QDialogButtonBox()
        self.copy_button = buttons.addButton(
            "&Copy instructions", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.copy_button.setAccessibleName("Copy planning guide instructions")
        self.save_button = buttons.addButton(
            "&Save guide...", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.save_button.setAccessibleName("Save planning guide")
        self.close_button = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.close_button.setAccessibleName("Close planning guide")
        self.copy_button.clicked.connect(self.copy_instructions)
        self.save_button.clicked.connect(self.save_guide)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def copy_instructions(self) -> None:
        QApplication.clipboard().setText(self.guide.instructions)
        self.status.setText("Instructions copied. No planning data was included.")

    def save_guide(self) -> None:
        name, _ = QFileDialog.getSaveFileName(
            self,
            "Save planning guide",
            "planacity-planning-guide.md",
            "Markdown (*.md)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not name:
            return
        path = Path(name)
        if not path.suffix:
            path = path.with_suffix(".md")
        if (
            path.exists()
            and QMessageBox.question(
                self,
                "Replace guide?",
                f"Replace '{path}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            path.write_text(self.guide.instructions, encoding="utf-8", newline="\n")
        except OSError as error:
            QMessageBox.warning(
                self,
                "Planning guide could not be saved",
                f"Could not save '{path}'.\n\n{error}\n\n"
                "Check the file and folder permissions, or choose another path.",
            )
            return
        self.status.setText(f"Guide saved to {path}")


class AboutDialog(QDialog):
    """Describe the application and link to the canonical packaged guide."""

    def __init__(
        self,
        parent: QWidget | None = None,
        guide_opener: Callable[[QWidget | None], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.guide = load_planning_guide()
        self._guide_opener = guide_opener or show_planning_guide
        self.setObjectName("aboutDialog")
        self.setWindowTitle("About Planacity")
        self.setModal(True)
        self.resize(560, 390)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        title = QLabel("Planacity")
        title.setProperty("role", "title")
        layout.addWidget(title)
        tagline = QLabel("Plan the work. Respect the capacity.")
        tagline.setProperty("role", "subtitle")
        layout.addWidget(tagline)
        version_label = QLabel(f"Development preview {self.guide.application_version}")
        version_label.setProperty("role", "badge")
        version_label.setAccessibleName(
            f"Planacity application version {self.guide.application_version}"
        )
        layout.addWidget(version_label)
        description = QLabel(
            "A local-first program planning workspace for engineering teams. Create and "
            "save plans, import and export Jira CSV, review timelines and dependencies, "
            "understand capacity and availability, manage shared events, and plan work "
            "against explicit sprints."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        local = QLabel(
            "Planning data stays local by default. No account, cloud service, telemetry, "
            "or network connection is required."
        )
        local.setWordWrap(True)
        local.setProperty("role", "muted")
        layout.addWidget(local)
        layout.addStretch()

        buttons = QDialogButtonBox()
        self.guide_button = buttons.addButton(
            "Planning with an &agent...", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.guide_button.setAccessibleName("Open Planning with an agent")
        self.close_button = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.guide_button.clicked.connect(lambda: self._guide_opener(self))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def show_planning_guide(parent: QWidget | None = None) -> None:
    PlanningGuideDialog(parent).exec()


def show_about(parent: QWidget | None = None) -> None:
    AboutDialog(parent).exec()


def planning_guide_shortcut() -> QKeySequence:
    """Keep the discoverable standard Help shortcut testable without a window."""
    return QKeySequence(QKeySequence.StandardKey.HelpContents)
