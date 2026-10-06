"""Program summary and compact analysis over the canonical plan snapshot."""

from collections.abc import Callable
from enum import StrEnum
from fractions import Fraction

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from planacity.planning.capacity_breakdown import CapacityLoadState
from planacity.planning.overview_analysis import OverviewAnalysis, calculate_overview_analysis
from planacity.ui.analysis_chart import AnalysisBar, AnalysisBarChart
from planacity.ui.pages import Panel, WorkspacePage, label
from planacity.ui.reservations import hours_text
from planacity.ui.session import Session


class AnalysisMode(StrEnum):
    PEOPLE = "people"
    TOPICS = "topics"
    BREAKDOWN = "breakdown"


class TopicMeasure(StrEnum):
    SCHEDULED = "scheduled"
    ESTIMATED = "estimated"


def _hours(value: Fraction | None) -> str:
    return "Unknown" if value is None else f"{hours_text(value)} h"


def _state_text(state: CapacityLoadState) -> str:
    return {
        CapacityLoadState.UNKNOWN: "Unknown",
        CapacityLoadState.INCOMPLETE: "Incomplete",
        CapacityLoadState.OVERLOADED: "Overloaded",
        CapacityLoadState.FULL: "Fully allocated",
        CapacityLoadState.WITHIN_CAPACITY: "Within capacity",
        CapacityLoadState.NO_WORK: "No allocated work",
        CapacityLoadState.NO_CAPACITY: "No planning capacity",
    }[state]


class OverviewPage(WorkspacePage):
    def __init__(
        self, session: Session, on_new: Callable[[], None], on_plan: Callable[[], None]
    ) -> None:
        super().__init__("Program overview", "Plan the work. Respect the capacity.")
        self.session = session
        self.analysis: OverviewAnalysis | None = None
        metrics = QHBoxLayout()
        self.values = []
        for title in ("Work items", "People", "Planning horizon"):
            panel = Panel(title)
            value = label("Not set", "heading")
            self.values.append(value)
            panel.content.addWidget(value)
            metrics.addWidget(panel)
        self.content.addLayout(metrics)

        panel = Panel("Program Plan")
        self.name = label("No project open", "title")
        self.description = label("Create a plan or open a local project from the File menu.")
        panel.content.addWidget(self.name)
        panel.content.addWidget(self.description)
        actions = QHBoxLayout()
        for title, callback in (("New plan...", on_new), ("View plan", on_plan)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        panel.content.addLayout(actions)
        self.content.addWidget(panel)

        self.analysis_group = QGroupBox("Analysis")
        self.analysis_group.setObjectName("overviewAnalysis")
        self.analysis_group.setAccessibleName("Program analysis")
        self.analysis_group.setCheckable(True)
        self.analysis_group.setChecked(True)
        group_layout = QVBoxLayout(self.analysis_group)
        group_layout.setContentsMargins(20, 24, 20, 20)
        group_layout.setSpacing(14)
        self.analysis_content = QWidget()
        analysis_layout = QVBoxLayout(self.analysis_content)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        analysis_layout.setSpacing(12)
        controls = QHBoxLayout()
        view_label = label("Analysis view")
        self.mode = QComboBox()
        self.mode.setAccessibleName("Analysis view")
        for title, enum_value in (
            ("Capacity by person", AnalysisMode.PEOPLE),
            ("Planned work by topic", AnalysisMode.TOPICS),
            ("Capacity breakdown", AnalysisMode.BREAKDOWN),
        ):
            self.mode.addItem(title, enum_value.value)
        view_label.setBuddy(self.mode)
        controls.addWidget(view_label)
        controls.addWidget(self.mode)
        self.measure_label = label("Topic measure")
        self.measure = QComboBox()
        self.measure.setAccessibleName("Planned work topic measure")
        self.measure.addItem("Scheduled allocated hours (plan horizon)", TopicMeasure.SCHEDULED)
        self.measure.addItem("Estimated leaf effort (whole plan)", TopicMeasure.ESTIMATED)
        self.measure_label.setBuddy(self.measure)
        controls.addWidget(self.measure_label)
        controls.addWidget(self.measure)
        controls.addStretch()
        analysis_layout.addLayout(controls)
        self.scope = label("Open a plan to calculate analysis.")
        self.scope.setAccessibleName("Analysis scope and date range")
        analysis_layout.addWidget(self.scope)
        self.legend = label(
            "Bar fill: measured hours. Dashed outline: planning-capacity reference. "
            "Hatching or dotted outlines: overload, unknown, or incomplete coverage."
        )
        self.legend.setAccessibleName("Analysis chart legend")
        analysis_layout.addWidget(self.legend)
        self.chart = AnalysisBarChart()
        analysis_layout.addWidget(self.chart)
        self.table = QTableView()
        self.table.setAccessibleName("Exact Overview analysis values")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(170)
        self.table.setMaximumHeight(280)
        self.model = QStandardItemModel(self)
        self.table.setModel(self.model)
        analysis_layout.addWidget(self.table)
        self.coverage = label("")
        self.coverage.setAccessibleName("Analysis coverage notes")
        analysis_layout.addWidget(self.coverage)
        group_layout.addWidget(self.analysis_content)
        self.analysis_group.toggled.connect(self.analysis_content.setVisible)
        self.content.addWidget(self.analysis_group)

        self.content.addWidget(
            label(
                "Use Import to bring in Jira CSV or export the agreed plan. "
                "Overview calculations never modify project data."
            )
        )
        self.content.addStretch()
        self.mode.currentIndexChanged.connect(self.refresh_analysis)
        self.measure.currentIndexChanged.connect(self.refresh_analysis)
        session.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        plan = self.session.document.plan
        if plan is None:
            self.analysis = None
            self.refresh_analysis()
            return
        self.name.setText(plan.name)
        self.description.setText(
            plan.description or "Add a description through File -> Plan properties."
        )
        for widget, value in zip(
            self.values,
            (
                str(len(plan.work_items)),
                str(len(plan.people)),
                f"{plan.horizon.start.isoformat()} to {plan.horizon.end.isoformat()}",
            ),
            strict=True,
        ):
            widget.setText(value)
        self.analysis = calculate_overview_analysis(plan)
        self.refresh_analysis()

    def refresh_analysis(self, *args: object) -> None:
        analysis = self.analysis
        mode = AnalysisMode(self.mode.currentData())
        topics = mode == AnalysisMode.TOPICS
        self.measure_label.setVisible(topics)
        self.measure.setVisible(topics)
        self.model.clear()
        if analysis is None:
            self.scope.setText("Open a plan to calculate analysis.")
            self.coverage.clear()
            self.chart.set_rows(())
            return
        self.scope.setText(
            f"Inclusive plan horizon: {analysis.period.start} to {analysis.period.end}. "
            "Scope: complete current plan; Plan and Timeline filters do not change these values."
        )
        self.coverage.setText("\n".join(f"- {message}" for message in analysis.coverage))
        if mode == AnalysisMode.PEOPLE:
            self._show_people(analysis)
        elif mode == AnalysisMode.TOPICS:
            self._show_topics(analysis)
        else:
            self._show_breakdown(analysis)
        for column in range(self.model.columnCount()):
            self.table.resizeColumnToContents(column)
        if self.model.columnCount():
            self.table.horizontalHeader().setSectionResizeMode(
                self.model.columnCount() - 1, QHeaderView.ResizeMode.Stretch
            )

    def _row(self, values: tuple[str, ...], stable_id: str) -> None:
        items = [QStandardItem(value) for value in values]
        for item in items:
            item.setEditable(False)
            item.setData(stable_id, Qt.ItemDataRole.UserRole)
        self.model.appendRow(items)

    def _show_people(self, analysis: OverviewAnalysis) -> None:
        self.model.setHorizontalHeaderLabels(
            (
                "Person",
                "Planning capacity",
                "Scheduled work",
                "Remaining",
                "Unplaced demand",
                "State and coverage",
            )
        )
        bars = []
        for person in analysis.people:
            state = _state_text(person.state)
            name = f"{person.name} [{str(person.person_id)[:8]}]"
            messages = "; ".join(person.gap_messages)
            self._row(
                (
                    name,
                    _hours(person.planning_hours),
                    _hours(person.scheduled_hours),
                    _hours(person.remaining_hours),
                    _hours(person.unplaced_hours),
                    f"{state}. {messages}" if messages else state,
                ),
                str(person.person_id),
            )
            bars.append(
                AnalysisBar(
                    name,
                    person.scheduled_hours,
                    f"Work {_hours(person.scheduled_hours)}; planning "
                    f"{_hours(person.planning_hours)}; remaining "
                    f"{_hours(person.remaining_hours)}; {state}",
                    reference=person.planning_hours,
                    incomplete=person.state
                    in (CapacityLoadState.UNKNOWN, CapacityLoadState.INCOMPLETE),
                )
            )
        self.chart.set_rows(tuple(bars))

    def _show_topics(self, analysis: OverviewAnalysis) -> None:
        measure = TopicMeasure(self.measure.currentData())
        if measure == TopicMeasure.SCHEDULED:
            self.model.setHorizontalHeaderLabels(
                ("Topic", "Scheduled allocated", "Unplaced demand", "Coverage")
            )
            bars = []
            for topic in analysis.topics:
                topic_label = (
                    f"{topic.label} [{str(topic.group_id)[:8]}]"
                    if topic.group_id is not None
                    else topic.label
                )
                self._row(
                    (
                        topic_label,
                        _hours(topic.scheduled_hours),
                        _hours(topic.unplaced_hours),
                        (
                            f"{topic.leaf_count} leaf item(s); "
                            f"{topic.missing_estimate_count} missing estimate(s)"
                        ),
                    ),
                    topic.key,
                )
                bars.append(
                    AnalysisBar(
                        topic_label,
                        topic.scheduled_hours,
                        f"Scheduled {_hours(topic.scheduled_hours)}; unplaced "
                        f"{_hours(topic.unplaced_hours)}",
                        incomplete=topic.unplaced_hours > 0,
                    )
                )
            self.chart.set_rows(tuple(bars))
            return
        self.model.setHorizontalHeaderLabels(
            ("Topic", "Estimated leaf effort", "Leaf items", "Missing estimates", "Scope")
        )
        bars = []
        for topic in analysis.topics:
            topic_label = (
                f"{topic.label} [{str(topic.group_id)[:8]}]"
                if topic.group_id is not None
                else topic.label
            )
            self._row(
                (
                    topic_label,
                    _hours(topic.estimated_leaf_hours),
                    str(topic.leaf_count),
                    str(topic.missing_estimate_count),
                    "Whole plan; estimates are not prorated by dates",
                ),
                topic.key,
            )
            bars.append(
                AnalysisBar(
                    topic_label,
                    topic.estimated_leaf_hours,
                    f"Estimated {_hours(topic.estimated_leaf_hours)}; "
                    f"{topic.missing_estimate_count} missing",
                    incomplete=topic.missing_estimate_count > 0,
                )
            )
        self.chart.set_rows(tuple(bars))

    def _show_breakdown(self, analysis: OverviewAnalysis) -> None:
        capacity = analysis.capacity
        rows: list[tuple[str, Fraction | None, str, str, Fraction | None]] = [
            (
                "Nominal calendar capacity",
                capacity.nominal_hours,
                "Known-roster subtotal before reductions",
                "nominal",
                None,
            ),
            (
                "Recorded unavailability",
                capacity.unavailable_hours,
                "Deduction from saved availability",
                "unavailable",
                None,
            ),
            (
                "Available before duties",
                capacity.available_hours,
                "Nominal capacity after recorded unavailability",
                "available",
                None,
            ),
        ]
        rows.extend(
            (
                f"Reservation: {reservation.name} [{str(reservation.rule_id)[:8]}]",
                reservation.hours,
                "Placed recurring reservation hours",
                str(reservation.rule_id),
                None,
            )
            for reservation in capacity.reservations
        )
        rows.extend(
            (
                (
                    "Planning capacity",
                    capacity.planning_hours,
                    "Available after duties",
                    "planning",
                    None,
                ),
                (
                    "Scheduled work",
                    capacity.scheduled_hours,
                    "Allocated work placed in the horizon",
                    "scheduled",
                    capacity.planning_hours,
                ),
                (
                    "Remaining capacity",
                    capacity.remaining_hours,
                    "Signed planning capacity after scheduled work",
                    "remaining",
                    None,
                ),
                (
                    "Unplaced demand",
                    capacity.unplaced_hours,
                    "Work or reservations that could not be placed",
                    "unplaced",
                    None,
                ),
            )
        )
        self.model.setHorizontalHeaderLabels(("Component", "Hours", "Interpretation"))
        bars = []
        for title, value, explanation, stable_id, reference in rows:
            self._row((title, _hours(value), explanation), stable_id)
            bars.append(
                AnalysisBar(
                    title,
                    value,
                    _hours(value),
                    reference=reference,
                    incomplete=capacity.partial or stable_id == "unplaced" and bool(value),
                )
            )
        self.chart.set_rows(tuple(bars))
