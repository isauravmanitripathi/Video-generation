import json
import os
from dataclasses import dataclass
from typing import Literal, Optional

ThemeName = Literal["dark", "light"]


@dataclass(frozen=True)
class AppSettings:
    theme: ThemeName = "dark"


class SettingsStore:
    """
    Very small JSON settings store.
    Writes to a local file so theme preference persists across restarts.
    """

    def __init__(self, settings_path: str):
        self.settings_path = settings_path

    def load(self) -> AppSettings:
        if not os.path.exists(self.settings_path):
            return AppSettings()
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            theme = data.get("theme", "dark")
            if theme not in ("dark", "light"):
                theme = "dark"
            return AppSettings(theme=theme)  # type: ignore[arg-type]
        except Exception:
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump({"theme": settings.theme}, f, indent=2)


def _qss_common() -> str:
    # Shared shapes/spacing so both themes feel consistent.
    return """
QWidget {
  font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
  font-size: 13px;
}

QMenuBar::item {
  padding: 6px 10px;
  border-radius: 6px;
}

QMenu {
  padding: 6px;
}
QMenu::item {
  padding: 6px 28px 6px 12px;
  border-radius: 6px;
}

QScrollBar:vertical {
  width: 12px;
  background: transparent;
}
QScrollBar::handle:vertical {
  border-radius: 6px;
  margin: 2px;
  min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
  height: 0;
}

QPushButton {
  padding: 8px 14px;
  border-radius: 8px;
}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
  border-radius: 8px;
  padding: 8px 10px;
}

QFrame#Card {
  border-radius: 12px;
}
QFrame#Card:hover {
  /* slight lift without shadow (Qt shadows are expensive) */
}

QRadioButton {
  spacing: 10px;
}
QRadioButton::indicator {
  width: 18px;
  height: 18px;
  border-radius: 9px;
}
"""


def qss_for_theme(theme: ThemeName) -> str:
    if theme == "light":
        return _qss_common() + """
QWidget { background-color: #f3f3f3; color: #202020; }

QMainWindow, QDialog { background-color: #f3f3f3; }

QMenuBar { background-color: #ffffff; border-bottom: 1px solid #e6e6e6; }
QMenuBar::item:selected { background-color: #e8f3ff; }

QMenu { background-color: #ffffff; border: 1px solid #d9d9d9; }
QMenu::item:selected { background-color: #0078d4; color: #ffffff; }

QPushButton {
  background-color: #ffffff;
  border: 1px solid #d1d1d1;
}
QPushButton:hover { background-color: #f7f7f7; border-color: #bcbcbc; }
QPushButton:pressed { background-color: #ededed; border-color: #bcbcbc; }
QPushButton:disabled { background-color: #f3f3f3; color: #9a9a9a; border-color: #e1e1e1; }

QPushButton#PrimaryButton {
  background-color: #0078d4;
  color: #ffffff;
  border: none;
}
QPushButton#PrimaryButton:hover { background-color: #106ebe; }
QPushButton#PrimaryButton:pressed { background-color: #005a9e; }
QPushButton#PrimaryButton:disabled { background-color: #d9d9d9; color: #9a9a9a; }

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
  background-color: #ffffff;
  border: 1px solid #d1d1d1;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
  border: 1px solid #0078d4;
}

QScrollBar::handle:vertical { background-color: #c7c7c7; }
QScrollBar::handle:vertical:hover { background-color: #a8a8a8; }

QFrame#Card { background-color: #ffffff; border: 1px solid #e1e1e1; }
QFrame#Card[checked="true"] { border: 2px solid #0078d4; }

QRadioButton::indicator { border: 2px solid #666666; background: transparent; }
QRadioButton::indicator:checked { border: 2px solid #0078d4; background: #0078d4; }
"""

    # default dark
    return _qss_common() + """
QWidget { background-color: #1f1f1f; color: #f1f1f1; }

QMainWindow, QDialog { background-color: #1f1f1f; }

QMenuBar { background-color: #202020; border-bottom: 1px solid #2b2b2b; }
QMenuBar::item:selected { background-color: #2a2a2a; }

QMenu { background-color: #202020; border: 1px solid #3a3a3a; }
QMenu::item:selected { background-color: #0078d4; color: #ffffff; }

QPushButton {
  background-color: #2a2a2a;
  border: 1px solid #3a3a3a;
}
QPushButton:hover { background-color: #333333; border-color: #4a4a4a; }
QPushButton:pressed { background-color: #3a3a3a; border-color: #5a5a5a; }
QPushButton:disabled { background-color: #252525; color: #777777; border-color: #2f2f2f; }

QPushButton#PrimaryButton {
  background-color: #0078d4;
  color: #ffffff;
  border: none;
}
QPushButton#PrimaryButton:hover { background-color: #106ebe; }
QPushButton#PrimaryButton:pressed { background-color: #005a9e; }
QPushButton#PrimaryButton:disabled { background-color: #2b2b2b; color: #7a7a7a; }

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
  background-color: #2a2a2a;
  border: 1px solid #3a3a3a;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
  border: 1px solid #0078d4;
}

QScrollBar::handle:vertical { background-color: #4a4a4a; }
QScrollBar::handle:vertical:hover { background-color: #5a5a5a; }

QFrame#Card { background-color: #242424; border: 1px solid #2f2f2f; }
QFrame#Card[checked="true"] { border: 2px solid #0078d4; }

QRadioButton::indicator { border: 2px solid #a0a0a0; background: transparent; }
QRadioButton::indicator:checked { border: 2px solid #0078d4; background: #0078d4; }
"""


def apply_theme(app, theme: ThemeName) -> None:
    """
    Apply global theme QSS to the QApplication.
    """
    app.setStyleSheet(qss_for_theme(theme))

