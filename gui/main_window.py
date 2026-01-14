import os
import shutil
from datetime import datetime
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QTextEdit, QComboBox, QFileDialog)
from PyQt5.QtCore import Qt
from gui.custom_widgets import LogPanel, ImageCanvas

class MainWindow(QMainWindow):
    def __init__(self, ratio_name):
        super().__init__()
        self.setWindowTitle("Video Content Generator")
        self.resize(1200, 800)
        
        # Ensure uploads dir
        self.uploads_dir = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(self.uploads_dir, exist_ok=True)
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # --- 1. Left Panel: Logs ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_container.setStyleSheet("background-color: #2b2b2b; color: #ddd;")
        
        self.log_panel = LogPanel()
        left_layout.addWidget(self.log_panel)
        self.log_panel.log(f"Application started. Mode: {ratio_name}")
        
        # --- 2. Center Panel: Image Canvas ---
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        # Removed setAlignment(Qt.AlignCenter) to allow canvas to expand
        center_container.setStyleSheet("background-color: #121212;")
        
        self.canvas = ImageCanvas(ratio_name)
        # Connect canvas signals
        self.canvas.log_signal.connect(self.log_panel.log)
        self.canvas.file_dropped_signal.connect(self.process_image_upload)
        
        center_layout.addWidget(self.canvas)
        
        # Upload Button below canvas
        btn_upload = QPushButton("Upload Image")
        btn_upload.setStyleSheet("""
            QPushButton {
                 background-color: #444; color: white; padding: 8px; border-radius: 4px; border: 1px solid #555;
            }
            QPushButton:hover { background-color: #555; }
        """)
        btn_upload.clicked.connect(self.open_upload_dialog)
        center_layout.addWidget(btn_upload)

        # Zoom Controls
        zoom_layout = QHBoxLayout()
        
        btn_zoom_out = QPushButton("−")  # Minus sign
        btn_zoom_out.setFixedSize(40, 40)
        btn_zoom_out.setStyleSheet("""
            QPushButton {
                background-color: #444; color: white; font-size: 20px; 
                font-weight: bold; border-radius: 4px; border: 1px solid #555;
            }
            QPushButton:hover { background-color: #555; }
        """)
        btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        zoom_layout.addWidget(btn_zoom_out)
        
        btn_reset_zoom = QPushButton("Reset")
        btn_reset_zoom.setStyleSheet("""
            QPushButton {
                background-color: #444; color: white; padding: 8px 16px; 
                border-radius: 4px; border: 1px solid #555;
            }
            QPushButton:hover { background-color: #555; }
        """)
        btn_reset_zoom.clicked.connect(self.canvas.reset_zoom)
        zoom_layout.addWidget(btn_reset_zoom)
        
        btn_zoom_in = QPushButton("+")  # Plus sign
        btn_zoom_in.setFixedSize(40, 40)
        btn_zoom_in.setStyleSheet("""
            QPushButton {
                background-color: #444; color: white; font-size: 20px; 
                font-weight: bold; border-radius: 4px; border: 1px solid #555;
            }
            QPushButton:hover { background-color: #555; }
        """)
        btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        zoom_layout.addWidget(btn_zoom_in)
        
        center_layout.addLayout(zoom_layout)

        
        # --- 3. Right Panel: Settings ---
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_container.setStyleSheet("background-color: #333; color: white;")
        
        lbl_settings = QLabel("Settings")
        lbl_settings.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        right_layout.addWidget(lbl_settings)
        
        # Script Input
        right_layout.addWidget(QLabel("Script:"))
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Enter video text...")
        right_layout.addWidget(self.text_input)
        
        # Voice Selection
        right_layout.addWidget(QLabel("Voice:"))
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(["Voice 1", "Voice 2", "Voice 3"])
        right_layout.addWidget(self.voice_combo)
        
        right_layout.addStretch()
        
        # Generate Button
        self.btn_generate = QPushButton("Generate Video")
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #5a9bd6; color: white; padding: 12px; 
                font-size: 16px; border-radius: 5px; font-weight: bold;
            }
            QPushButton:hover { background-color: #4a8bc6; }
        """)
        self.btn_generate.clicked.connect(lambda: self.log_panel.log("Generate clicked (Not implemented yet)"))
        right_layout.addWidget(self.btn_generate)
        
        # Add to Main Layout with Ratios
        # Left (1), Center (2), Right (1)
        main_layout.addWidget(left_container, 20)
        main_layout.addWidget(center_container, 60) # Bigger focus on canvas
        main_layout.addWidget(right_container, 20)
        
    def open_upload_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            self.process_image_upload(file_path)

    def process_image_upload(self, file_path):
        try:
            filename = os.path.basename(file_path)
            # Create unique name to prevent overwrites? Or keep original.
            # Let's verify if file exists, maybe append timestamp
            name, ext = os.path.splitext(filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_filename = f"{name}_{timestamp}{ext}"
            
            target_path = os.path.join(self.uploads_dir, new_filename)
            
            shutil.copy2(file_path, target_path)
            
            self.canvas.set_image(target_path)
            self.log_panel.log(f"Image uploaded & saved to: {new_filename}")
            
        except Exception as e:
            self.log_panel.log(f"Error processing upload: {str(e)}")

