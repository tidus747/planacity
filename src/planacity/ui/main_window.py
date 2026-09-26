"""Desktop navigation, appearance preferences, and the planning workspace shell."""

from functools import partial
from importlib.metadata import version

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
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

from planacity.ui.icons import navigation_icon
from planacity.ui.pages import import_page, label, overview_page, work_page
from planacity.ui.theme import COLORS, Theme, stylesheet


class MainWindow(QMainWindow):
    """Keep presentation preferences separate from future program data."""

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings("Planacity", "Planacity")
        self.setWindowTitle("Planacity")
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
        for page in (
            overview_page(partial(self.show_page, 1), partial(self.show_page, 2)),
            work_page(),
            work_page(people=True),
            import_page(),
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        self._menus()
        self.statusBar().showMessage("Development preview · No project open")
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
        brand = QHBoxLayout()
        mark = QLabel("P")
        mark.setObjectName("brandMark")
        mark.setFixedSize(32, 32)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(mark)
        name = QLabel("Planacity")
        name.setObjectName("brand")
        brand.addWidget(name)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(25)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for index, name_text in enumerate(("Overview", "Plan", "People", "Import")):
            button = QPushButton("  " + name_text)
            button.setAccessibleName(name_text)
            button.setProperty("role", "nav")
            button.setCheckable(True)
            button.setIconSize(QSize(22, 22))
            button.clicked.connect(partial(self.show_page, index))
            group.addButton(button)
            self.navigation[name_text] = button
            layout.addWidget(button)
        self.navigation["Import"].setToolTip("Jira CSV import is planned for v0.2.")
        layout.addSpacing(20)
        divider = QFrame()
        divider.setProperty("role", "divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addSpacing(10)
        layout.addWidget(label("PROJECT", "eyebrow"))
        layout.addWidget(label("No project open", "heading"))
        layout.addWidget(label("Planning Foundation\nv0.1 preview"))
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
        file_menu = self.menuBar().addMenu("&File")
        for title in ("&New plan…", "&Open…", "&Save", "Save &as…"):
            action = file_menu.addAction(title)
            action.setEnabled(False)
            action.setToolTip("Project creation and persistence are coming in v0.1.")
        file_menu.addSeparator()
        quit_action = file_menu.addAction("E&xit")
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction("Plan editing is coming in v0.1").setEnabled(False)
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
            "Respect the capacity.</p><p>Planning Foundation development preview. "
            "Plan editing and saving are not available yet.</p>",
        )

    def show_page(self, index: int) -> None:
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
