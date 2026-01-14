import os
import shutil
from datetime import datetime
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QTextEdit, QComboBox, QFileDialog,
                             QScrollArea, QFrame, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from gui.custom_widgets import LogPanel, ImageCanvas
from generation.video_generator import generate_video_from_snippets

class VideoGeneratorWorker(QThread):
    """Background thread for video generation."""
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    
    def __init__(self, image_path, snippets, output_path, aspect_ratio):
        super().__init__()
        self.image_path = image_path
        self.snippets = snippets
        self.output_path = output_path
        self.aspect_ratio = aspect_ratio
    
    def run(self):
        self.progress.emit("Generating video with Ken Burns effect...")
        success, message = generate_video_from_snippets(
            self.image_path,
            self.snippets,
            self.output_path,
            self.aspect_ratio,
            progress_callback=lambda msg: self.progress.emit(msg)
        )
        self.finished.emit(success, message)


class MainWindow(QMainWindow):
    def __init__(self, ratio_name):
        super().__init__()
        self.setWindowTitle("Video Content Generator")
        self.resize(1200, 800)
        self.ratio_name = ratio_name  # Store for video generation
        self.current_image_path = None  # Track current image
        self.video_worker = None  # Video generation thread
        
        # Ensure uploads dir
        self.uploads_dir = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(self.uploads_dir, exist_ok=True)
        
        # Output directory for videos
        self.output_dir = os.path.join(os.getcwd(), 'output')
        os.makedirs(self.output_dir, exist_ok=True)
        
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
        
        # Upload and Snip Buttons
        btn_row = QHBoxLayout()
        
        btn_upload = QPushButton("Upload Image")
        btn_upload.setStyleSheet("""
            QPushButton {
                 background-color: #444; color: white; padding: 8px; border-radius: 4px; border: 1px solid #555;
            }
            QPushButton:hover { background-color: #555; }
        """)
        btn_upload.clicked.connect(self.open_upload_dialog)
        btn_row.addWidget(btn_upload)
        
        self.btn_snip = QPushButton("✂ Snip")
        self.btn_snip.setCheckable(True)
        self.btn_snip.setStyleSheet("""
            QPushButton {
                background-color: #444; color: white; padding: 8px; border-radius: 4px; border: 1px solid #555;
            }
            QPushButton:hover { background-color: #555; }
            QPushButton:checked { background-color: #e74c3c; border: 2px solid #c0392b; }
        """)
        self.btn_snip.clicked.connect(self.toggle_snip_mode)
        btn_row.addWidget(self.btn_snip)
        
        center_layout.addLayout(btn_row)


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
        
        # === Snippets Section ===
        lbl_snippets = QLabel("Snippets")
        lbl_snippets.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        right_layout.addWidget(lbl_snippets)
        
        # Scrollable container for snippet buttons
        snippets_scroll = QScrollArea()
        snippets_scroll.setWidgetResizable(True)
        snippets_scroll.setMaximumHeight(200)
        snippets_scroll.setStyleSheet("""
            QScrollArea { border: 1px solid #555; background-color: #2a2a2a; }
        """)
        
        self.snippets_container = QWidget()
        self.snippets_layout = QVBoxLayout(self.snippets_container)
        self.snippets_layout.setContentsMargins(5, 5, 5, 5)
        self.snippets_layout.setSpacing(5)
        self.snippets_layout.addStretch()
        
        snippets_scroll.setWidget(self.snippets_container)
        right_layout.addWidget(snippets_scroll)
        
        # Connect canvas signals
        self.canvas.snippet_created.connect(self.on_snippet_created)
        self.snippet_buttons = []  # Track buttons
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #555;")
        right_layout.addWidget(separator)
        
        # Script Input
        right_layout.addWidget(QLabel("Script:"))
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Enter video text...")
        self.text_input.setMaximumHeight(100)
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
            QPushButton:disabled { background-color: #666; }
        """)
        self.btn_generate.clicked.connect(self.generate_video)
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
            
            self.current_image_path = target_path  # Track for video generation
            self.canvas.set_image(target_path)
            self.log_panel.log(f"Image uploaded & saved to: {new_filename}")
            
            # Clear snippets when new image is loaded
            self.canvas.clear_snippets()
            self._clear_snippet_buttons()
            
        except Exception as e:
            self.log_panel.log(f"Error processing upload: {str(e)}")
    
    def _clear_snippet_buttons(self):
        """Clear all snippet buttons from UI."""
        for btn_row in self.snippet_buttons:
            self.snippets_layout.removeWidget(btn_row)
            btn_row.deleteLater()
        self.snippet_buttons.clear()

    def toggle_snip_mode(self):
        """Toggle snip mode on the canvas."""
        enabled = self.btn_snip.isChecked()
        self.canvas.set_snip_mode(enabled)
    
    def on_snippet_created(self, idx, coords):
        """Called when a new snippet is created on the canvas."""
        # Create button row with snippet button and delete button
        btn_row = QWidget()
        row_layout = QHBoxLayout(btn_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(3)
        
        # Get color from canvas
        color = self.canvas.snippets[idx]['color']
        color_hex = color.name()
        
        btn_snippet = QPushButton(f"Snippet {idx + 1}")
        btn_snippet.setStyleSheet(f"""
            QPushButton {{
                background-color: {color_hex}; color: white; padding: 5px 10px;
                border-radius: 3px; text-align: left; font-weight: bold;
            }}
            QPushButton:hover {{ opacity: 0.8; }}
        """)
        btn_snippet.clicked.connect(lambda checked, i=idx: self.on_snippet_click(i))
        row_layout.addWidget(btn_snippet, stretch=1)
        
        btn_delete = QPushButton("×")
        btn_delete.setFixedSize(25, 25)
        btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #666; color: white; border-radius: 3px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #e74c3c; }
        """)
        btn_delete.clicked.connect(lambda checked, i=idx: self.on_snippet_delete(i))
        row_layout.addWidget(btn_delete)
        
        # Insert before the stretch
        self.snippets_layout.insertWidget(self.snippets_layout.count() - 1, btn_row)
        self.snippet_buttons.append(btn_row)
    
    def on_snippet_click(self, idx):
        """Select a snippet on the canvas."""
        self.canvas.select_snippet(idx)
    
    def on_snippet_delete(self, idx):
        """Delete a snippet."""
        if 0 <= idx < len(self.snippet_buttons):
            # Remove button widget
            btn_row = self.snippet_buttons.pop(idx)
            self.snippets_layout.removeWidget(btn_row)
            btn_row.deleteLater()
            
            # Delete from canvas
            self.canvas.delete_snippet(idx)
            
            # Update remaining button indices
            self._refresh_snippet_buttons()
    
    def _refresh_snippet_buttons(self):
        """Refresh snippet button indices after deletion."""
        for i, btn_row in enumerate(self.snippet_buttons):
            layout = btn_row.layout()
            btn_snippet = layout.itemAt(0).widget()
            color = self.canvas.snippets[i]['color']
            color_hex = color.name()
            btn_snippet.setText(f"Snippet {i + 1}")
            btn_snippet.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color_hex}; color: white; padding: 5px 10px;
                    border-radius: 3px; text-align: left; font-weight: bold;
                }}
                QPushButton:hover {{ opacity: 0.8; }}
            """)
            # Reconnect with correct index
            btn_snippet.clicked.disconnect()
            btn_snippet.clicked.connect(lambda checked, idx=i: self.on_snippet_click(idx))
            
            btn_delete = layout.itemAt(1).widget()
            btn_delete.clicked.disconnect()
            btn_delete.clicked.connect(lambda checked, idx=i: self.on_snippet_delete(idx))

    def generate_video(self):
        """Generate Ken Burns video from current image and snippets."""
        # Validate inputs
        if not self.current_image_path or not os.path.exists(self.current_image_path):
            self.log_panel.log("Error: No image loaded. Please upload an image first.")
            QMessageBox.warning(self, "No Image", "Please upload an image first.")
            return
        
        if not self.canvas.snippets:
            self.log_panel.log("Error: No snippets defined. Create at least one snippet.")
            QMessageBox.warning(self, "No Snippets", "Please create at least one snippet using the Snip tool.")
            return
        
        # Prepare output path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"kenburns_{timestamp}.mp4"
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Prepare snippets data
        snippets_data = []
        for snippet in self.canvas.snippets:
            rect = snippet['source_rect']
            snippets_data.append({
                'x': rect.x(),
                'y': rect.y(),
                'width': rect.width(),
                'height': rect.height()
            })
        
        # Disable button during generation
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Generating...")
        
        # Start worker thread
        self.video_worker = VideoGeneratorWorker(
            self.current_image_path,
            snippets_data,
            output_path,
            self.ratio_name
        )
        self.video_worker.progress.connect(self.on_video_progress)
        self.video_worker.finished.connect(self.on_video_finished)
        self.video_worker.start()
        
        self.log_panel.log(f"Starting video generation with {len(snippets_data)} snippets...")
    
    def on_video_progress(self, message):
        """Handle video generation progress."""
        self.log_panel.log(message)
    
    def on_video_finished(self, success, message):
        """Handle video generation completion."""
        # Re-enable button
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("Generate Video")
        
        self.log_panel.log(message)
        
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.warning(self, "Error", message)

