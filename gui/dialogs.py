from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QButtonGroup, 
                             QRadioButton, QPushButton, QHBoxLayout, QFrame,
                             QCheckBox, QWidget)
from PyQt5.QtCore import Qt, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QBrush


class ToggleSwitch(QWidget):
    """A modern animated toggle switch widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 28)
        self.setCursor(Qt.PointingHandCursor)
        
        self._checked = False
        self._circle_position = 3  # Start position (OFF)
        
        # Animation for smooth toggle
        self._animation = QPropertyAnimation(self, b"circle_position", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
    
    def get_circle_position(self):
        return self._circle_position
    
    def set_circle_position(self, pos):
        self._circle_position = pos
        self.update()
    
    circle_position = pyqtProperty(int, get_circle_position, set_circle_position)
    
    def isChecked(self):
        return self._checked
    
    def setChecked(self, checked):
        self._checked = checked
        # Animate to new position
        end_pos = 27 if checked else 3
        self._animation.stop()
        self._animation.setStartValue(self._circle_position)
        self._animation.setEndValue(end_pos)
        self._animation.start()
    
    def mousePressEvent(self, event):
        self._checked = not self._checked
        end_pos = 27 if self._checked else 3
        self._animation.stop()
        self._animation.setStartValue(self._circle_position)
        self._animation.setEndValue(end_pos)
        self._animation.start()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background track
        if self._checked:
            track_color = QColor("#4CAF50")  # Green when ON
        else:
            track_color = QColor("#555555")  # Gray when OFF
        
        painter.setBrush(QBrush(track_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, 52, 28, 14, 14)
        
        # Circle (knob)
        painter.setBrush(QBrush(QColor("white")))
        painter.drawEllipse(self._circle_position, 3, 22, 22)


class OptionRow(QWidget):
    """A row containing a label, description, and toggle switch."""
    
    def __init__(self, title, description, default_on=False, parent=None):
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        # Left side - text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        text_layout.addWidget(self.title_label)
        
        self.desc_label = QLabel(description)
        self.desc_label.setStyleSheet("font-size: 11px; color: #aaa;")
        self.desc_label.setWordWrap(True)
        text_layout.addWidget(self.desc_label)
        
        layout.addLayout(text_layout, stretch=1)
        
        # Right side - toggle
        self.toggle = ToggleSwitch()
        self.toggle.setChecked(default_on)
        layout.addWidget(self.toggle)
    
    def is_checked(self):
        return self.toggle.isChecked()


class VideoOptionsDialog(QDialog):
    """Dialog for configuring video generation options."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video Options")
        self.setFixedWidth(400)
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QLabel("Configure Video Options")
        header.setStyleSheet("""
            font-size: 16px; 
            font-weight: bold; 
            color: white; 
            padding: 20px;
            background-color: #333;
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Options container
        options_container = QWidget()
        options_container.setStyleSheet("background-color: #2b2b2b;")
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(0)
        options_layout.setContentsMargins(0, 10, 0, 10)
        
        # === Option Rows ===
        
        # Ken Burns Effect
        self.ken_burns_row = OptionRow(
            "Ken Burns Effect",
            "Smooth zoom & pan animation between snippets",
            default_on=False
        )
        options_layout.addWidget(self.ken_burns_row)
        
        # Divider
        divider1 = QFrame()
        divider1.setFrameShape(QFrame.HLine)
        divider1.setStyleSheet("background-color: #444; margin: 0 15px;")
        divider1.setFixedHeight(1)
        options_layout.addWidget(divider1)
        
        # Box Overlay
        self.box_overlay_row = OptionRow(
            "Box Overlay",
            "Show border rectangles around snippet regions",
            default_on=False
        )
        options_layout.addWidget(self.box_overlay_row)
        
        layout.addWidget(options_container)
        
        # Buttons
        btn_container = QWidget()
        btn_container.setStyleSheet("background-color: #333; padding: 15px;")
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(15, 15, 15, 15)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                padding: 10px 25px;
                border-radius: 5px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_layout.addStretch()
        
        btn_generate = QPushButton("Generate Video")
        btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #5a9bd6;
                color: white;
                padding: 10px 25px;
                border-radius: 5px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a8bc6;
            }
        """)
        btn_generate.clicked.connect(self.accept)
        btn_layout.addWidget(btn_generate)
        
        layout.addWidget(btn_container)
    
    def get_options(self):
        """Return dictionary of all selected options."""
        return {
            'ken_burns': self.ken_burns_row.is_checked(),
            'show_boxes': self.box_overlay_row.is_checked()
        }


class AspectRatioDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Select Video Size")
        self.setFixedSize(300, 200)
        
        layout = QVBoxLayout()
        
        label = QLabel("Choose the aspect ratio for your video:")
        layout.addWidget(label)
        
        self.ratio_group = QButtonGroup(self)
        
        self.rb_reel = QRadioButton("Reel (9:16)")
        self.rb_youtube = QRadioButton("YouTube (16:9)")
        self.rb_square = QRadioButton("Square (1:1)")
        
        self.rb_reel.setChecked(True) # Default
        
        layout.addWidget(self.rb_reel)
        layout.addWidget(self.rb_youtube)
        layout.addWidget(self.rb_square)
        
        self.ratio_group.addButton(self.rb_reel)
        self.ratio_group.addButton(self.rb_youtube)
        self.ratio_group.addButton(self.rb_square)
        
        btn_confirm = QPushButton("Confirm")
        btn_confirm.clicked.connect(self.accept)
        layout.addWidget(btn_confirm)
        
        self.setLayout(layout)
        
    def get_selected_ratio(self):
        if self.rb_reel.isChecked():
            return "Reel (9:16)"
        elif self.rb_youtube.isChecked():
            return "YouTube (16:9)"
        else:
            return "Square (1:1)"

