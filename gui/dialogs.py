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
            track_color = QColor("#0078d4")  # Windows blue when ON
        else:
            track_color = QColor("#c1c1c1")  # Gray when OFF
        
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
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #202020;")
        text_layout.addWidget(self.title_label)
        
        self.desc_label = QLabel(description)
        self.desc_label.setStyleSheet("font-size: 12px; color: #666666;")
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
        self.setWindowTitle("Video Options - VideoForge")
        self.setFixedWidth(480)
        self.setStyleSheet("""
            QDialog {
                background-color: #fafafa;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QLabel("Video Generation Options")
        header.setStyleSheet("""
            QLabel {
                font-size: 20px; 
                font-weight: 600; 
                color: #202020; 
                padding: 24px;
                background-color: #ffffff;
                border-bottom: 1px solid #e1e1e1;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Options container
        options_container = QWidget()
        options_container.setStyleSheet("background-color: #fafafa;")
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(0)
        options_layout.setContentsMargins(0, 16, 0, 16)
        
        # === Option Rows ===
        
        # Zoom to Snippets (NEW)
        self.zoom_row = OptionRow(
            "Zoom to Snippets",
            "Camera zooms in to each snippet. Turn OFF to show full image.",
            default_on=True
        )
        options_layout.addWidget(self.zoom_row)
        
        # Divider
        divider0 = QFrame()
        divider0.setFrameShape(QFrame.HLine)
        divider0.setStyleSheet("background-color: #e1e1e1; margin: 0 16px;")
        divider0.setFixedHeight(1)
        options_layout.addWidget(divider0)
        
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
        divider1.setStyleSheet("background-color: #e1e1e1; margin: 0 16px;")
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
        
        # Info label for when zoom is off
        self.info_label = QLabel()
        self.info_label.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 12px;
                padding: 12px 16px;
                background-color: #e8f4f8;
                border-left: 3px solid #0078d4;
            }
        """)
        self.info_label.setWordWrap(True)
        self.info_label.hide()
        layout.addWidget(self.info_label)
        
        # Connect zoom toggle to update other options
        self.zoom_row.toggle.mousePressEvent = self._on_zoom_toggle
        
        # Buttons
        btn_container = QWidget()
        btn_container.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-top: 1px solid #e1e1e1;
            }
        """)
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(20, 16, 20, 16)
        btn_layout.setSpacing(12)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #202020;
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 400;
                border: 1px solid #d1d1d1;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border-color: #b1b1b1;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_layout.addStretch()
        
        btn_generate = QPushButton("Generate Video")
        btn_generate.setCursor(Qt.PointingHandCursor)
        btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 400;
                border: none;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
        btn_generate.clicked.connect(self.accept)
        btn_layout.addWidget(btn_generate)
        
        layout.addWidget(btn_container)
    
    def _on_zoom_toggle(self, event):
        """Handle zoom toggle - disable Ken Burns when zoom is off."""
        # Call original toggle behavior
        toggle = self.zoom_row.toggle
        toggle._checked = not toggle._checked
        end_pos = 27 if toggle._checked else 3
        toggle._animation.stop()
        toggle._animation.setStartValue(toggle._circle_position)
        toggle._animation.setEndValue(end_pos)
        toggle._animation.start()
        
        # If zoom is turned off, disable Ken Burns and show info
        if not toggle._checked:
            self.ken_burns_row.toggle.setChecked(False)
            self.ken_burns_row.setEnabled(False)
            self.box_overlay_row.toggle.setChecked(True)
            self.info_label.setText("Zoom OFF: Full image shown with box overlays. Sub-images will appear/disappear at their positions.")
            self.info_label.show()
        else:
            self.ken_burns_row.setEnabled(True)
            self.info_label.hide()
    
    def get_options(self):
        """Return dictionary of all selected options."""
        use_zoom = self.zoom_row.is_checked()
        ken_burns = self.ken_burns_row.is_checked() if use_zoom else False
        
        return {
            'use_zoom': use_zoom,
            'ken_burns': ken_burns,
            'show_boxes': self.box_overlay_row.is_checked()
        }


class AspectRatioDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoForge - Select Aspect Ratio")
        self.setFixedSize(520, 380)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Choose an aspect ratio")
        title.setStyleSheet("QLabel { font-size: 22px; font-weight: 600; }")
        layout.addWidget(title)

        subtitle = QLabel("This sets the video canvas size for this session.")
        subtitle.setStyleSheet("QLabel { color: palette(mid); }")
        layout.addWidget(subtitle)
        
        self.ratio_group = QButtonGroup(self)

        self.rb_reel = QRadioButton("Reel (9:16)")
        self.rb_reel.setChecked(True)
        card_reel = self._make_ratio_card(self.rb_reel, "Best for Shorts / Reels / TikTok")

        self.rb_youtube = QRadioButton("YouTube (16:9)")
        card_yt = self._make_ratio_card(self.rb_youtube, "Standard landscape video")

        self.rb_square = QRadioButton("Square (1:1)")
        card_sq = self._make_ratio_card(self.rb_square, "Feeds and square layouts")

        layout.addWidget(card_reel)
        layout.addWidget(card_yt)
        layout.addWidget(card_sq)

        self.ratio_group.addButton(self.rb_reel)
        self.ratio_group.addButton(self.rb_youtube)
        self.ratio_group.addButton(self.rb_square)

        layout.addStretch(1)

        footer_layout = QHBoxLayout()
        btn_confirm = QPushButton("Continue")
        btn_confirm.setCursor(Qt.PointingHandCursor)
        btn_confirm.setObjectName("PrimaryButton")
        btn_confirm.clicked.connect(self.accept)
        footer_layout.addStretch(1)
        footer_layout.addWidget(btn_confirm)
        layout.addLayout(footer_layout)

        self.ratio_group.buttonClicked.connect(self._sync_ratio_cards)
        self._sync_ratio_cards()

    def _make_ratio_card(self, radio: QRadioButton, subtitle: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setProperty("checked", False)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(6)

        radio.setStyleSheet("QRadioButton { font-size: 15px; font-weight: 600; }")
        sub = QLabel(subtitle)
        sub.setStyleSheet("QLabel { color: palette(mid); }")

        card_layout.addWidget(radio)
        card_layout.addWidget(sub)

        # click anywhere
        card.mousePressEvent = lambda e, r=radio: r.setChecked(True)
        return card

    def _sync_ratio_cards(self):
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            w = item.widget()
            if isinstance(w, QFrame) and w.objectName() == "Card":
                rb = w.findChild(QRadioButton)
                w.setProperty("checked", bool(rb and rb.isChecked()))
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()
        
    def get_selected_ratio(self):
        if self.rb_reel.isChecked():
            return "Reel (9:16)"
        elif self.rb_youtube.isChecked():
            return "YouTube (16:9)"
        else:
            return "Square (1:1)"

