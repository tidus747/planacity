"""Small validated forms; invalid drafts stay open for correction."""

from collections.abc import Callable
from typing import TypeVar

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPersistentModelIndex, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from planacity.ui.plan_model import PlanModel

T = TypeVar("T")


def validated_form(
    parent: QWidget, title: str, fields: list[tuple[str, QWidget]], build: Callable[[], T]
) -> T | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(440)
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    for name, widget in fields:
        form.addRow(name, widget)
    layout.addLayout(form)
    error = QLabel()
    error.setWordWrap(True)
    error.setAccessibleName("Validation error")
    layout.addWidget(error)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(buttons)
    result: list[T] = []

    def accept() -> None:
        try:
            result.append(build())
        except ValueError as problem:
            error.setText(str(problem))
            return
        dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return result[0] if accepted else None


class ValidatedDelegate(QStyledItemDelegate):
    """Do not close an inline editor while its draft fails domain validation."""

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        editor = QLineEdit(parent)
        editor.setProperty("planIndex", QPersistentModelIndex(index))
        return editor

    def eventFilter(self, editor: QObject, event: QEvent) -> bool:
        if (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            index = editor.property("planIndex")
            if isinstance(index, QPersistentModelIndex):
                model = index.model()
                if isinstance(model, PlanModel):
                    model.error.emit("")
        commit = event.type() == QEvent.Type.FocusOut or (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key()
            in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
        )
        if commit and isinstance(editor, QLineEdit):
            index = editor.property("planIndex")
            if isinstance(index, QPersistentModelIndex) and index.isValid():
                model = index.model()
                if isinstance(model, PlanModel):
                    try:
                        model.candidate(index, editor.text())
                    except ValueError as error:
                        model.error.emit(str(error))
                        QTimer.singleShot(0, editor.setFocus)
                        return True
        return super().eventFilter(editor, event)
