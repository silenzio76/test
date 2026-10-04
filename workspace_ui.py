"""Shared native styling and headings for the desktop workspace."""
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def heading(title, description):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    label = QLabel(title)
    label.setObjectName('sectionTitle')
    layout.addWidget(label)
    detail = QLabel(description)
    detail.setWordWrap(True)
    detail.setObjectName('sectionDescription')
    layout.addWidget(detail)
    return widget


def apply_workspace_style(window):
    window.setFont(QFont('Segoe UI', 10))
    window.setStyleSheet('''
        QMainWindow, QWidget#workspaceRoot { background: #f3f5f4; }
        QLabel { color: #243d36; }
        QLabel#sectionTitle { font-size: 22px; font-weight: 600; }
        QLabel#sectionDescription { color: #596b65; }
        QLabel#datasetContext { padding: 8px 12px; background: #e6eeea; color: #344f44; }
        QTabWidget#workspaceTabs::pane { border: 1px solid #d3ded8; background: #ffffff; }
        QTabBar::tab { padding: 8px 12px; background: #e8eeeb; color: #40594f; }
        QTabBar::tab:selected { background: #ffffff; color: #1e4d3b; border-bottom: 2px solid #2f7257; }
        QTabBar::tab:hover { background: #f4f8f5; }
        QGroupBox { font-weight: 600; border: 1px solid #d3ded8; border-radius: 5px;
                    margin-top: 10px; padding: 12px 8px 8px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        QPushButton { padding: 6px 10px; border: 1px solid #bbcfc3; border-radius: 4px;
                      background: #ffffff; color: #254c3c; }
        QPushButton:hover { background: #edf5ef; border-color: #649a7c; }
        QPushButton:pressed { background: #dbece1; }
        QPushButton:disabled { color: #7c8e85; background: #edf0ee; border-color: #d4ded8; }
        QPushButton[primary="true"] { background: #2f7257; color: #ffffff; border-color: #2f7257; }
        QPushButton[primary="true"]:hover { background: #245c46; }
        QPushButton[primary="true"]:disabled { color: #7c8e85; background: #edf0ee; border-color: #d4ded8; }
        QPushButton:focus, QComboBox:focus, QLineEdit:focus, QDateTimeEdit:focus,
        QSpinBox:focus, QTableView:focus { border: 2px solid #428468; }
        QLineEdit, QComboBox, QSpinBox, QDateTimeEdit { padding: 4px; }
        QTableView { background: #ffffff; alternate-background-color: #f1f6f3;
                     gridline-color: #dde6e0; selection-background-color: #d5e9dc;
                     selection-color: #203d2e; }
        QHeaderView::section { background: #edf3ef; padding: 5px; border: 0;
                              border-right: 1px solid #d3ded8; color: #365343; }
        QSplitter::handle { background: #e3ece6; }
    ''')
