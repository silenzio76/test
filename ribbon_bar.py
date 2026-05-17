"""
Ribbon Bar personalizzato per HealthReport Studio.
Fornisce funzioni generali organizzate in gruppi.
"""

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QToolButton,
    QLabel,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from pathlib import Path


class RibbonGroup(QFrame):
    """Gruppo di pulsanti della ribbon bar."""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        #self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        
        # Titolo del gruppo
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 9px; font-weight: bold; color: #666;")
        
        # Layout per i pulsanti
        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setSpacing(4)
        self.buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addLayout(self.buttons_layout)
        layout.addWidget(title_label)
    
    def add_button(self, icon_path: str, tooltip: str, callback=None) -> QToolButton:
        """Aggiungi un pulsante al gruppo."""
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setIconSize(QSize(24, 24))
        button.setMinimumSize(32, 32)
        
        # Carica l'icona SVG
        if Path(icon_path).exists():
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                button.setIcon(QIcon(pixmap))
        
        if callback:
            button.clicked.connect(callback)
        
        self.buttons_layout.addWidget(button)
        return button


class RibbonBar(QWidget):
    """Ribbon bar personalizzata per HealthReport Studio."""
    
    # Segnali per le azioni
    new_pressed = Signal()
    open_pressed = Signal()
    save_pressed = Signal()
    import_pressed = Signal()
    export_pressed = Signal()
    print_pressed = Signal()
    refresh_pressed = Signal()
    settings_pressed = Signal()
    help_pressed = Signal()
    about_pressed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        """Inizializza l'interfaccia della ribbon bar."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        
        # Gruppo File
        file_group = RibbonGroup("File")
        self.new_btn = file_group.add_button(
            "icons/new.svg", "Nuovo progetto", self.new_pressed.emit
        )
        self.open_btn = file_group.add_button(
            "icons/open.svg", "Apri file", self.open_pressed.emit
        )
        self.save_btn = file_group.add_button(
            "icons/save.svg", "Salva", self.save_pressed.emit
        )
        main_layout.addWidget(file_group)
        
        # Gruppo Dati
        data_group = RibbonGroup("Dati")
        self.import_btn = data_group.add_button(
            "icons/import.svg", "Importa dataset", self.import_pressed.emit
        )
        self.export_btn = data_group.add_button(
            "icons/export.svg", "Esporta dataset", self.export_pressed.emit
        )
        self.refresh_btn = data_group.add_button(
            "icons/refresh.svg", "Aggiorna", self.refresh_pressed.emit
        )
        main_layout.addWidget(data_group)
        
        # Gruppo Report
        report_group = RibbonGroup("Report")
        self.print_btn = report_group.add_button(
            "icons/print.svg", "Stampa report", self.print_pressed.emit
        )
        main_layout.addWidget(report_group)
        
        # Gruppo Strumenti
        tools_group = RibbonGroup("Strumenti")
        self.settings_btn = tools_group.add_button(
            "icons/settings.svg", "Impostazioni", self.settings_pressed.emit
        )
        self.help_btn = tools_group.add_button(
            "icons/help.svg", "Aiuto", self.help_pressed.emit
        )
        self.about_btn = tools_group.add_button(
            "icons/about.svg", "Informazioni", self.about_pressed.emit
        )
        main_layout.addWidget(tools_group)
        
        # Spazio elastico
        main_layout.addStretch()
        
        # Stile della ribbon bar per adattarsi al tema dell'applicazione
        self.setAutoFillBackground(True)
        self.setStyleSheet("""
            RibbonBar {
                background-color: palette(window);
                border-bottom: 1px solid palette(mid);
            }
            QFrame {
                background-color: palette(base);
                border: 1px solid palette(midlight);
                border-radius: 4px;
            }
            QLabel {
                color: palette(text);
            }
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 2px;
            }
            QToolButton:hover {
                background-color: palette(highlight);
                border: 1px solid palette(dark);
            }
            QToolButton:pressed {
                background-color: palette(mid);
                border: 1px solid palette(dark);
            }
        """)
