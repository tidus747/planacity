"""Desktop navigation, appearance preferences, and the planning workspace shell."""

from functools import partial
from importlib.metadata import version

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from planacity.ui.editor_pages import PeoplePage, PlanPage
from planacity.ui.icons import image_icon, image_pixmap, navigation_icon
from planacity.ui.jira_pages import ChangesPage, ImportPage
from planacity.ui.overview import OverviewPage
from planacity.ui.pages import label
from planacity.ui.project_actions import ProjectActions
from planacity.ui.session import Session
from planacity.ui.theme import COLORS, Theme, stylesheet


class MainWindow(QMainWindow):
    """Share one document while keeping appearance preferences separate from project data."""

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings("Planacity", "Planacity")
        self.session = Session()
        self.setWindowTitle("Planacity")
        self.setWindowIcon(image_icon("planacity-mark.png"))
        self.resize(1280, 840)
        self.setMinimumSize(960, 640)
        self.navigation: dict[str, QPushButton] = {}
        self.theme_buttons: dict[Theme, QPushButton] = {}
        self.theme_actions: dict[Theme, QAction] = {}
        self.pages = QStackedWidget()
        self.pages.setObjectName("workspace")

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar())
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.plan_page = PlanPage(self.session)
        self.people_page = PeoplePage(self.session)
        for page in (
            OverviewPage(self.session, lambda: self.file_actions.new(), partial(self.show_page, 1)),
            self.plan_page,
            self.people_page,
            ImportPage(self.session),
            ChangesPage(self.session),
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        self._menus()
        self.session.changed.connect(self._refresh_document)
        self.statusBar().showMessage("Development preview | No project open")
        self.statusBar().addPermanentWidget(label(f"Planacity {version('planacity')}", "eyebrow"))
        default = (
            Theme.DARK
            if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
            else Theme.LIGHT
        )
        stored = self.settings.value("appearance/theme", default.value)
        theme = (
            Theme(stored)
            if isinstance(stored, str) and stored in (Theme.LIGHT.value, Theme.DARK.value)
            else default
        )
        self.set_theme(theme, persist=False)
        self.show_page(0)

    def _sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(212)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 25, 14, 18)
        layout.setSpacing(8)
        self.brand_logo = QLabel()
        self.brand_logo.setObjectName("brandLogo")
        self.brand_logo.setAccessibleName("Planacity")
        self.brand_logo.setFixedSize(184, 70)
        self.brand_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wordmark = image_pixmap("planacity-wordmark.png").scaled(
            QSize(164, 55),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.brand_logo.setPixmap(wordmark)
        layout.addWidget(self.brand_logo)
        layout.addSpacing(17)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for index, name_text in enumerate(("Overview", "Plan", "People", "Import", "Changes")):
            button = QPushButton("  " + name_text)
            button.setAccessibleName(name_text)
            button.setProperty("role", "nav")
            button.setCheckable(True)
            button.setIconSize(QSize(22, 22))
            button.clicked.connect(partial(self.show_page, index))
            group.addButton(button)
            self.navigation[name_text] = button
            layout.addWidget(button)
        self.navigation["Import"].setToolTip("Import and export Jira CSV files.")
        layout.addSpacing(20)
        divider = QFrame()
        divider.setProperty("role", "divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addSpacing(10)
        layout.addWidget(label("PROJECT", "eyebrow"))
        self.project_label = label("No project open", "heading")
        layout.addWidget(self.project_label)
        layout.addWidget(label("Jira Roundtrip\nv0.2 preview"))
        layout.addStretch()
        layout.addWidget(label("APPEARANCE", "eyebrow"))
        modes = QHBoxLayout()
        modes.setSpacing(6)
        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        for theme in Theme:
            button = QPushButton(theme.value.title())
            button.setAccessibleName(f"Use {theme.value} appearance")
            button.setCheckable(True)
            button.clicked.connect(partial(self.set_theme, theme))
            mode_group.addButton(button)
            self.theme_buttons[theme] = button
            modes.addWidget(button)
        layout.addLayout(modes)
        return sidebar

    def _menus(self) -> None:
        self.file_actions = ProjectActions(self, self.session)
        self.file_actions.flush_edit = self.plan_page.commit_editor
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction("Plan properties...", self.file_actions.properties)
        edit_menu.addAction("Move selected work...", self.plan_page.move_item)
        edit_menu.addAction("Delete selected work...", self.plan_page.delete_item)
        view_menu = self.menuBar().addMenu("&View")
        for index, name in enumerate(self.navigation):
            action = view_menu.addAction(name)
            action.setShortcut(QKeySequence(f"Ctrl+{index + 1}"))
            action.triggered.connect(partial(self.show_page, index))
        view_menu.addSeparator()
        appearance = view_menu.addMenu("&Appearance")
        group = QActionGroup(self)
        group.setExclusive(True)
        for theme in Theme:
            action = appearance.addAction(theme.value.title())
            action.setCheckable(True)
            action.triggered.connect(partial(self.set_theme, theme))
            group.addAction(action)
            self.theme_actions[theme] = action
        about = self.menuBar().addMenu("&Help").addAction("About Planacity")
        about.triggered.connect(self._about)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About Planacity",
            "<b>Planacity</b><p>Plan the work. "
            "Respect the capacity.</p><p>Jira Roundtrip development preview. "
            "Create, edit, and save local Program Plans. "
            "Import and export Jira CSV. Capacity remains planned for later versions.</p>",
        )

    def _refresh_document(self) -> None:
        document = self.session.document
        if document.plan is None:
            return
        self.project_label.setText(document.plan.name)
        marker = " *" if document.dirty else ""
        self.setWindowTitle(f"{document.plan.name}{marker} - Planacity")
        location = str(document.path) if document.path else "Not saved yet"
        self.statusBar().showMessage(
            f"{'Unsaved changes' if document.dirty else 'Saved'} | {location}"
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.file_actions.guard():
            event.accept()
        else:
            event.ignore()

    def show_page(self, index: int) -> None:
        if index != 1 and not self.plan_page.commit_editor():
            list(self.navigation.values())[self.pages.currentIndex()].setChecked(True)
            return
        self.pages.setCurrentIndex(index)
        list(self.navigation.values())[index].setChecked(True)
        self._refresh_icons()

    def set_theme(self, theme: Theme, *, persist: bool = True) -> None:
        self.theme = theme
        scheme = Qt.ColorScheme.Dark if theme == Theme.DARK else Qt.ColorScheme.Light
        QGuiApplication.styleHints().setColorScheme(scheme)
        self.setStyleSheet(stylesheet(theme))
        self.theme_buttons[theme].setChecked(True)
        self.theme_actions[theme].setChecked(True)
        self._refresh_icons()
        if persist:
            self.settings.setValue("appearance/theme", theme.value)
            self.settings.sync()
            if self.settings.status() != QSettings.Status.NoError:
                self.statusBar().showMessage(
                    "Appearance changed, but the preference could not be saved."
                )

    def _refresh_icons(self) -> None:
        colors = COLORS[self.theme]
        for name, button in self.navigation.items():
            color = colors.accent if button.isChecked() else colors.text
            button.setIcon(navigation_icon(name, color))
