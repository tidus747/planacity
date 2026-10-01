"""Small validated forms; invalid drafts stay open for correction."""

from collections.abc import Callable
from typing import TypeVar

from PySide6.QtCore import (
    QDate,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from planacity.ui.calendars import PlanacityCalendar
from planacity.ui.icons import svg_icon
from planacity.ui.plan_filter_model import PlanFilterModel
from planacity.ui.plan_model import PlanModel

T = TypeVar("T")


class CalendarLineEdit(QLineEdit):
    """Keep optional ISO text entry while offering a mouse-friendly calendar."""

    date_selected = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.calendar_action = QAction(
            svg_icon("calendar.svg", "#208bad"), "Choose date from calendar", self
        )
        self.calendar_action.setToolTip("Choose date from calendar")
        self.addAction(self.calendar_action, QLineEdit.ActionPosition.TrailingPosition)
        self.calendar_action.triggered.connect(self.show_calendar)
        self._calendar_menu: QMenu | None = None

    def show_calendar(self) -> None:
        """Open the picker at the typed date, or today when the draft is empty or invalid."""
        if self._calendar_menu is not None:
            self._calendar_menu.close()
        menu = QMenu(self)
        menu.setAccessibleName("Date picker")
        calendar = PlanacityCalendar(menu)
        calendar.setAccessibleName("Date calendar")
        current = QDate.fromString(self.text().strip(), Qt.DateFormat.ISODate)
        calendar.setSelectedDate(current if current.isValid() else QDate.currentDate())
        widget_action = QWidgetAction(menu)
        widget_action.setDefaultWidget(calendar)
        menu.addAction(widget_action)
        calendar.clicked.connect(self._select_date)
        menu.aboutToHide.connect(self._calendar_closed)
        self._calendar_menu = menu
        self.setProperty("calendarOpen", True)
        menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def _select_date(self, selected: QDate) -> None:
        self.setText(selected.toString(Qt.DateFormat.ISODate))
        if self._calendar_menu is not None:
            self._calendar_menu.close()
        QTimer.singleShot(0, self.date_selected.emit)

    def _calendar_closed(self) -> None:
        self.setProperty("calendarOpen", False)
        menu, self._calendar_menu = self._calendar_menu, None
        if menu is not None:
            menu.deleteLater()
        QTimer.singleShot(0, self.setFocus)


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
        editor = CalendarLineEdit(parent) if index.column() in (3, 4) else QLineEdit(parent)
        editor.setProperty("planIndex", QPersistentModelIndex(index))
        if isinstance(editor, CalendarLineEdit):
            editor.date_selected.connect(lambda: self._commit_calendar_date(editor))
        return editor

    @staticmethod
    def _validate(editor: QLineEdit) -> bool:
        index = editor.property("planIndex")
        if not isinstance(index, QPersistentModelIndex) or not index.isValid():
            return True
        model = index.model()
        if not isinstance(model, (PlanModel, PlanFilterModel)):
            return True
        try:
            model.candidate(index, editor.text())
        except ValueError as error:
            model.error.emit(str(error))
            QTimer.singleShot(0, editor.setFocus)
            return False
        return True

    def _commit_calendar_date(self, editor: CalendarLineEdit) -> None:
        if not self._validate(editor):
            return
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)

    def eventFilter(self, editor: QObject, event: QEvent) -> bool:
        if (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            index = editor.property("planIndex")
            if isinstance(index, QPersistentModelIndex):
                model = index.model()
                if isinstance(model, (PlanModel, PlanFilterModel)):
                    model.error.emit("")
        if event.type() == QEvent.Type.FocusOut and bool(editor.property("calendarOpen")):
            return False
        commit = event.type() == QEvent.Type.FocusOut or (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key()
            in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
        )
        if commit and isinstance(editor, QLineEdit):
            if not self._validate(editor):
                return True
        return super().eventFilter(editor, event)
