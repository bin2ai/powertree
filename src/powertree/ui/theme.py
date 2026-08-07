"""Application-wide dark theme (QSS)."""

APP_QSS = """
* { font-family: 'Segoe UI'; font-size: 12px; }
QMainWindow, QDialog { background: #0f1218; }
QWidget { background: #0f1218; color: #e8ecf5; }
QToolBar { background: #131722; border: none; padding: 3px; spacing: 3px; }
QToolBar::separator { background: #2c3650; width: 1px; margin: 4px 6px; }
QToolButton { background: transparent; border: 1px solid transparent;
              border-radius: 5px; padding: 4px 7px; color: #e8ecf5; }
QToolButton:hover { background: #1c2333; border-color: #2c3650; }
QToolButton:pressed, QToolButton:checked { background: #24304a; }
QMenuBar { background: #131722; }
QMenuBar::item { padding: 4px 10px; background: transparent; }
QMenuBar::item:selected { background: #24304a; border-radius: 4px; }
QMenu { background: #171c28; border: 1px solid #2c3650; padding: 4px; }
QMenu::item { padding: 5px 24px 5px 12px; border-radius: 4px; }
QMenu::item:selected { background: #24304a; }
QMenu::separator { height: 1px; background: #2c3650; margin: 4px 8px; }
QDockWidget { color: #e8ecf5; titlebar-close-icon: none; }
QDockWidget::title { background: #131722; padding: 6px 10px;
                     border-bottom: 1px solid #2c3650; font-weight: 600; }
QStatusBar { background: #131722; border-top: 1px solid #2c3650;
             color: #98a3b8; }
QLineEdit, QPlainTextEdit, QTextEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: #171c28; border: 1px solid #2c3650; border-radius: 5px;
    padding: 4px 6px; selection-background-color: #7c5cff; }
QLineEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus,
QComboBox:focus { border-color: #7c5cff; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #171c28; border: 1px solid #2c3650;
                              selection-background-color: #24304a; }
QPushButton { background: #1c2333; border: 1px solid #2c3650;
              border-radius: 5px; padding: 5px 12px; }
QPushButton:hover { background: #24304a; border-color: #3b4a6b; }
QPushButton:pressed { background: #2c3a58; }
QTreeWidget, QTreeView, QListWidget, QTableWidget {
    background: #131722; alternate-background-color: #161b26;
    border: 1px solid #232b3d; border-radius: 6px; }
QTreeWidget::item, QTreeView::item { padding: 3px 2px; }
QTreeWidget::item:selected, QTreeView::item:selected {
    background: #2c3a58; color: #ffffff; }
QHeaderView::section { background: #1a2030; color: #98a3b8; border: none;
    border-right: 1px solid #232b3d; border-bottom: 1px solid #2c3650;
    padding: 5px 6px; font-weight: 600; }
QTabWidget::pane { border: 1px solid #232b3d; border-radius: 6px;
                   top: -1px; }
QTabBar::tab { background: #131722; border: 1px solid #232b3d;
    border-bottom: none; padding: 6px 16px; border-top-left-radius: 6px;
    border-top-right-radius: 6px; margin-right: 2px; color: #98a3b8; }
QTabBar::tab:selected { background: #1c2333; color: #ffffff; }
QScrollBar:vertical { background: #131722; width: 11px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #2c3650; border-radius: 5px;
                              min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3b4a6b; }
QScrollBar:horizontal { background: #131722; height: 11px; }
QScrollBar::handle:horizontal { background: #2c3650; border-radius: 5px;
                                min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QSplitter::handle { background: #232b3d; }
QToolTip { background: #171c28; color: #e8ecf5; border: 1px solid #3b4a6b;
           padding: 6px; border-radius: 4px; }
QMessageBox { background: #171c28; }
"""


def apply_theme(app):
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
