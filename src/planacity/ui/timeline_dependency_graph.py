"""Accessible native-Qt dependency neighbourhood for the Timeline."""

from uuid import UUID

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from planacity.planning.dependency_neighborhood import (
    DependencyGraphCard,
    DependencyNeighborhood,
)


def _short_title(title: str, limit: int = 52) -> str:
    return title if len(title) <= limit else title[: limit - 3].rstrip() + "..."


def _card_description(card: DependencyGraphCard) -> str:
    parts = [
        f"{card.kind.value.title()}: {card.title}",
        card.dates,
        card.assignment,
    ]
    if not card.visible_in_timeline:
        parts.append("Hidden by current Timeline filters; activate to reveal it.")
    parts.extend(f"Warning: {warning}" for warning in card.warnings)
    return "\n".join(parts)


class TimelineDependencyGraph(QFrame):
    """Render one bounded predecessor -> selected -> successor neighbourhood."""

    navigate_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "panel")
        self.setAccessibleName("Selected work dependency graph")
        self.setMaximumHeight(310)
        self.card_buttons: dict[UUID, list[QPushButton]] = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(8)
        header = QHBoxLayout()
        heading = QLabel("Selected dependency graph")
        heading.setProperty("role", "heading")
        header.addWidget(heading)
        self.summary = QLabel("Select work to inspect its immediate dependencies.")
        self.summary.setProperty("role", "muted")
        self.summary.setWordWrap(True)
        header.addWidget(self.summary, 1)
        self._layout.addLayout(header)
        self.body = QWidget()
        self.body_layout = QHBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        self._layout.addWidget(self.body, 1)
        self.set_neighborhood(None)

    def _clear_body(self) -> None:
        self.card_buttons.clear()
        while self.body_layout.count():
            child = self.body_layout.takeAt(0)
            if child is None:
                break
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _button(self, card: DependencyGraphCard, *, selected: bool = False) -> QPushButton:
        hidden = " | hidden by filters" if not card.visible_in_timeline else ""
        warning = ""
        if card.warnings:
            more = f" (+{len(card.warnings) - 1} more)" if len(card.warnings) > 1 else ""
            warning = f"\nWarning: {_short_title(card.warnings[0], 58)}{more}"
        button = QPushButton(
            f"{_short_title(card.title)}\n{card.dates}\n{card.assignment}{hidden}{warning}"
        )
        button.setCheckable(selected)
        button.setChecked(selected)
        button.setMinimumWidth(220)
        button.setMaximumWidth(340)
        button.setMinimumHeight(82 if card.warnings else 66)
        description = _card_description(card)
        button.setAccessibleName(description.replace("\n", ". "))
        button.setToolTip(description)
        button.clicked.connect(
            lambda checked=False, item_id=card.item_id: self.navigate_requested.emit(str(item_id))
        )
        self.card_buttons.setdefault(card.item_id, []).append(button)
        return button

    def _column(
        self,
        title: str,
        cards: tuple[DependencyGraphCard, ...],
        omitted: tuple[DependencyGraphCard, ...] = (),
        *,
        selected: bool = False,
    ) -> QWidget:
        contents = QWidget()
        contents.setObjectName("dependencyGraphColumn")
        contents.setStyleSheet("QWidget#dependencyGraphColumn { background: transparent; }")
        layout = QVBoxLayout(contents)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        label = QLabel(title)
        label.setProperty("role", "muted")
        layout.addWidget(label)
        if cards:
            for card in cards:
                layout.addWidget(self._button(card, selected=selected))
        else:
            empty = QLabel("None")
            empty.setProperty("role", "muted")
            layout.addWidget(empty)
        if omitted:
            chooser = QComboBox()
            chooser.setAccessibleName(f"{title} omitted from graph")
            chooser.addItem(f"{len(omitted)} more - choose to navigate", "")
            for card in omitted:
                suffix = " (hidden by filters)" if not card.visible_in_timeline else ""
                chooser.addItem(card.title + suffix, str(card.item_id))
            chooser.activated.connect(
                lambda index, box=chooser: self._omitted_activated(box, index)
            )
            layout.addWidget(chooser)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.viewport().setObjectName("dependencyGraphViewport")
        scroll.viewport().setStyleSheet(
            "QWidget#dependencyGraphViewport { background: transparent; }"
        )
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(contents)
        scroll.setMinimumWidth(235)
        return scroll

    def _omitted_activated(self, chooser: QComboBox, index: int) -> None:
        item_id = chooser.itemData(index)
        if item_id:
            self.navigate_requested.emit(item_id)
            chooser.setCurrentIndex(0)

    def set_neighborhood(self, graph: DependencyNeighborhood | None) -> None:
        self._clear_body()
        if graph is None:
            self.summary.setText("Select work to inspect its immediate dependencies.")
            self.body_layout.addWidget(QLabel("No selected work."))
            self.setAccessibleDescription(self.summary.text())
            return

        statuses = []
        if graph.cycle_edges:
            statuses.append(f"{graph.cycle_edges} cycle edge(s)")
        if graph.conflict_edges:
            statuses.append(f"{graph.conflict_edges} date conflict(s)")
        if graph.unevaluated_edges:
            statuses.append(f"{graph.unevaluated_edges} unevaluated edge(s)")
        omitted = len(graph.omitted_predecessors) + len(graph.omitted_successors)
        if omitted:
            statuses.append(f"{omitted} neighbour(s) in the navigation lists")
        self.summary.setText(
            f"{len(graph.predecessors)} predecessor(s) -> selected -> "
            f"{len(graph.successors)} successor(s)"
            + (" | " + " | ".join(statuses) if statuses else "")
        )
        self.body_layout.addWidget(
            self._column("Predecessors", graph.predecessors, graph.omitted_predecessors), 1
        )
        self.body_layout.addWidget(QLabel("->"))
        self.body_layout.addWidget(self._column("Selected", (graph.selected,), selected=True), 1)
        self.body_layout.addWidget(QLabel("->"))
        self.body_layout.addWidget(
            self._column("Successors", graph.successors, graph.omitted_successors), 1
        )
        description = self.summary.text() + ". Activate any card to select and recenter it."
        self.setAccessibleDescription(description)
