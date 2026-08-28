"""Presentation-only visual tokens for the desktop application."""

APP_STYLESHEET = """
QMainWindow, QWidget { background: #07111a; color: #d7e4ee; font-family: Segoe UI, Arial; }
QTabWidget::pane { border: 1px solid #173244; background: #091722; }
QTabBar::tab { background: #091722; color: #a8bac7; padding: 11px 24px; border: 1px solid #10293a; }
QTabBar::tab:selected { background: #0a2941; color: #e7f5ff; border-bottom: 2px solid #1ba8f2; }
QGroupBox { border: 1px solid #173244; border-radius: 5px; margin-top: 10px; padding: 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #b8cedd; }
QLineEdit, QComboBox, QListWidget, QTableView { background: #08151f; border: 1px solid #254457; border-radius: 4px; padding: 6px; }
QPushButton { background: #102c3e; border: 1px solid #28536b; border-radius: 4px; padding: 7px 12px; }
QPushButton:hover { background: #16435d; }
QPushButton:disabled { background: #0a1b26; border-color: #16303f; color: #4d616e; }
QPushButton#primary { background: #0878c4; border-color: #1ca7f2; color: white; font-weight: 600; }
QPushButton#primary:disabled { background: #0d2c40; border-color: #16303f; color: #4d616e; }
QLabel#heading { color: #edf7ff; font-size: 18px; font-weight: 600; }
QLabel#muted { color: #91a8b7; }
QFrame#panel { border: 1px solid #173244; border-radius: 6px; background: #091722; }
QStatusBar { background: #061019; color: #90a9b7; border-top: 1px solid #173244; }
"""
