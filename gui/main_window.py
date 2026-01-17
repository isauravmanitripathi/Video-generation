import os
import shutil
import json
from datetime import datetime
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QTextEdit, QComboBox, QFileDialog,
                             QScrollArea, QFrame, QMessageBox, QMenuBar, QMenu, QAction,
                             QActionGroup, QToolBar, QDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from gui.custom_widgets import LogPanel, ImageCanvas, SnippetItemWidget
from gui.dialogs import AspectRatioDialog, VideoOptionsDialog
from generation.video_generator import generate_video_from_snippets
from audio.tts_handler import TTSHandler

class VideoGeneratorWorker(QThread):
    """Background thread for video generation."""
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    
    def __init__(self, image_path, snippets, output_path, aspect_ratio, tts_handler, voice="en-US-AriaNeural", show_boxes=False, ken_burns=True):
        super().__init__()
        self.image_path = image_path
        self.snippets = snippets
        self.output_path = output_path
        self.aspect_ratio = aspect_ratio
        self.tts_handler = tts_handler
        self.voice = voice
        self.show_boxes = show_boxes
        self.ken_burns = ken_burns
    
    def run(self):
        # Step 1: Generate Audio
        self.progress.emit("Step 1/2: Generating Audio...")
        
        # Audio directory
        audio_dir = os.path.join(os.path.dirname(self.output_path), "temp_audio")
        os.makedirs(audio_dir, exist_ok=True)
        
        snippets_with_audio = []
        
        for i, snippet in enumerate(self.snippets):
            snippets_with_audio.append(snippet.copy())
            text = snippet.get('text', '').strip()
            
            if text:
                self.progress.emit(f"Generating audio for snippet {i+1}...")
                audio_filename = f"audio_{i}_{datetime.now().strftime('%H%M%S')}.mp3"
                audio_path = os.path.join(audio_dir, audio_filename)
                
                success, duration = self.tts_handler.generate_audio(text, self.voice, audio_path)
                
                if success:
                    snippets_with_audio[i]['audio_path'] = audio_path
                    snippets_with_audio[i]['audio_duration'] = duration
                else:
                    self.progress.emit(f"Failed to generate audio for snippet {i+1}")
            else:
                snippets_with_audio[i]['audio_path'] = None
                snippets_with_audio[i]['audio_duration'] = 0.0

        # Step 2: Generate Video
        self.progress.emit("Step 2/2: Generating Video...")
        success, message = generate_video_from_snippets(
            self.image_path,
            snippets_with_audio,
            self.output_path,
            self.aspect_ratio,
            self.show_boxes,
            self.ken_burns,
            progress_callback=lambda msg: self.progress.emit(msg)
        )
        
        # Cleanup temp audio
        # shutil.rmtree(audio_dir, ignore_errors=True) # Keep for debugging or cleanup later
        
        self.finished.emit(success, message)


class MainWindow(QMainWindow):
    def __init__(self, ratio_name):
        super().__init__()
        self.setWindowTitle("Video Content Generator")
        self.resize(1200, 800)
        self.ratio_name = ratio_name  # Store for video generation
        self.current_image_path = None  # Track current image
        self.video_worker = None  # Video generation thread
        self.tts_handler = TTSHandler()
        self.snippet_widgets = []  # replacing self.snippet_buttons
        self.pending_snippets = []  # Queue of imported but unassigned snippets
        self.selected_pending_idx = None  # Currently selected pending snippet awaiting region
        
        # Ensure uploads dir
        self.uploads_dir = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(self.uploads_dir, exist_ok=True)
        
        # Output directory for videos
        self.output_dir = os.path.join(os.getcwd(), 'output')
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Setup Menu Bar
        self._setup_menu_bar()
        
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
        
        lbl_settings = QLabel("✦ Storyboard")
        lbl_settings.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #5a9bd6;")
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
        
        # Custom Script Input Removed - scripts are now per-snippet
        # Voice selection moved to top menu bar
        
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
        
    def _setup_menu_bar(self):
        """Setup the top menu bar with voice selection."""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #2b2b2b;
                color: white;
                padding: 5px;
                font-size: 13px;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 8px 15px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: #444;
            }
            QMenu {
                background-color: #333;
                color: white;
                border: 1px solid #555;
            }
            QMenu::item {
                padding: 8px 25px 8px 15px;
            }
            QMenu::item:selected {
                background-color: #5a9bd6;
            }
            QMenu::indicator {
                width: 18px;
                height: 18px;
                margin-left: 5px;
            }
            QMenu::indicator:checked {
                image: none;
                background-color: #5a9bd6;
                border-radius: 3px;
            }
        """)
        
        # Voice Menu
        voice_menu = menubar.addMenu("🎙 Voice")
        
        # Create action group for exclusive selection
        self.voice_action_group = QActionGroup(self)
        self.voice_action_group.setExclusive(True)
        
        # Add voice options
        voices = self.tts_handler.get_voices()
        self.selected_voice = voices[0] if voices else "en-US-AriaNeural"
        
        for voice in voices:
            action = QAction(voice, self)
            action.setCheckable(True)
            action.setData(voice)
            if voice == self.selected_voice:
                action.setChecked(True)
            action.triggered.connect(lambda checked, v=voice: self._on_voice_selected(v))
            self.voice_action_group.addAction(action)
            voice_menu.addAction(action)
        
        # Files Menu
        files_menu = menubar.addMenu("📁 Files")
        
        upload_json_action = QAction("Upload JSON", self)
        upload_json_action.triggered.connect(self._on_upload_json)
        files_menu.addAction(upload_json_action)
    
    def _on_voice_selected(self, voice):
        """Handle voice selection from menu."""
        self.selected_voice = voice
        self.log_panel.log(f"Voice changed to: {voice}")
    
    def _on_upload_json(self):
        """Handle JSON file upload from Files menu."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select JSON File", 
            "", 
            "JSON Files (*.json)"
        )
        if file_path:
            self._parse_json_snippets(file_path)
    
    def _parse_json_snippets(self, file_path):
        """Parse JSON file and create snippet widgets immediately."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate structure
            if 'snippets' not in data:
                self.log_panel.log("Error: JSON must have 'snippets' array")
                QMessageBox.warning(self, "Invalid JSON", "JSON file must contain a 'snippets' array.")
                return
            
            snippets = data['snippets']
            if not isinstance(snippets, list) or len(snippets) == 0:
                self.log_panel.log("Error: 'snippets' must be a non-empty array")
                QMessageBox.warning(self, "Invalid JSON", "'snippets' must be a non-empty array.")
                return
            
            # Clear existing snippets
            self._clear_snippet_buttons()
            self.canvas.clear_snippets()
            self.pending_snippets.clear()
            
            # Create snippet widgets for each imported snippet
            colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e91e63', '#00bcd4']
            
            for i, snippet in enumerate(snippets):
                if 'text' in snippet:
                    color_hex = colors[i % len(colors)]
                    
                    # Store pending snippet data
                    self.pending_snippets.append({
                        'id': snippet.get('id', str(i + 1)),
                        'text': snippet['text'],
                        'assigned': False,
                        'widget_idx': i,
                        'color': color_hex
                    })
                    
                    # Create widget (without canvas snippet yet)
                    widget = SnippetItemWidget(i, color_hex, text=snippet['text'])
                    widget.clicked.connect(self._on_pending_snippet_click)
                    widget.deleted.connect(self._on_pending_snippet_delete)
                    widget.text_changed.connect(self._on_pending_text_changed)
                    
                    # Mark as unassigned visually
                    widget.btn_header.setText(f"📍 Snippet {i+1} (click to assign region)")
                    
                    self.snippets_layout.addWidget(widget)
                    self.snippet_widgets.append(widget)
            
            title = data.get('title', 'Untitled Project')
            self.log_panel.log(f"Imported '{title}' with {len(self.pending_snippets)} snippets.")
            self.log_panel.log("Click a snippet, then draw its region on the image.")
            
            QMessageBox.information(
                self, 
                "JSON Imported", 
                f"Created {len(self.pending_snippets)} snippets.\n\n"
                "Workflow:\n"
                "1. Click a snippet in the Storyboard\n"
                "2. Click 'Snip' and draw the region on the image\n"
                "3. Repeat for each snippet"
            )
            
        except json.JSONDecodeError as e:
            self.log_panel.log(f"Error: Invalid JSON format - {e}")
            QMessageBox.warning(self, "JSON Error", f"Invalid JSON format:\n{e}")
        except Exception as e:
            self.log_panel.log(f"Error parsing JSON: {e}")
            QMessageBox.warning(self, "Error", f"Failed to parse JSON:\n{e}")
    
    def _on_pending_snippet_click(self, idx):
        """Handle click on a pending (unassigned) snippet."""
        if 0 <= idx < len(self.pending_snippets):
            pending = self.pending_snippets[idx]
            if not pending['assigned']:
                # Set this as the snippet awaiting region assignment
                self.selected_pending_idx = idx
                self.log_panel.log(f"Selected snippet {idx+1}. Now draw its region on the image.")
                
                # Enable snip mode automatically
                self.btn_snip.setChecked(True)
                self.canvas.set_snip_mode(True)
                
                # Highlight the selected widget
                for i, widget in enumerate(self.snippet_widgets):
                    if i == idx:
                        widget.btn_header.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {pending['color']}; 
                                color: white; 
                                padding: 8px;
                                border: 3px solid #fff;
                                border-radius: 4px;
                                text-align: left;
                                font-weight: bold;
                            }}
                        """)
                    elif i < len(self.pending_snippets) and not self.pending_snippets[i]['assigned']:
                        widget.btn_header.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {self.pending_snippets[i]['color']}; 
                                color: white; 
                                padding: 8px;
                                border: 1px solid #444;
                                border-radius: 4px;
                                text-align: left;
                                font-weight: bold;
                            }}
                        """)
            else:
                # Already assigned, just select on canvas
                self.canvas.select_snippet(idx)
    
    def _on_pending_snippet_delete(self, idx):
        """Delete a pending snippet."""
        if 0 <= idx < len(self.snippet_widgets):
            widget = self.snippet_widgets.pop(idx)
            self.snippets_layout.removeWidget(widget)
            widget.deleteLater()
            
            if idx < len(self.pending_snippets):
                self.pending_snippets.pop(idx)
            
            # Update indices
            for i, w in enumerate(self.snippet_widgets):
                w.update_index(i)
    
    def _on_pending_text_changed(self, idx, text):
        """Handle text change on pending snippet."""
        if 0 <= idx < len(self.pending_snippets):
            self.pending_snippets[idx]['text'] = text
    
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
        for widget in self.snippet_widgets:
            self.snippets_layout.removeWidget(widget)
            widget.deleteLater()
        self.snippet_widgets.clear()

    def toggle_snip_mode(self):
        """Toggle snip mode on the canvas."""
        enabled = self.btn_snip.isChecked()
        self.canvas.set_snip_mode(enabled)
    
    def on_snippet_created(self, idx, coords):
        """Called when a new snippet region is drawn on the canvas."""
        # Check if we're assigning a region to a pending snippet
        if self.selected_pending_idx is not None and self.selected_pending_idx < len(self.pending_snippets):
            pending = self.pending_snippets[self.selected_pending_idx]
            
            if not pending['assigned']:
                # Get the canvas snippet that was just created
                canvas_snippet = self.canvas.snippets[idx]
                
                # Store the source_rect and text in the canvas snippet
                canvas_snippet['text'] = pending['text']
                
                # Mark pending as assigned
                pending['assigned'] = True
                pending['canvas_idx'] = idx
                
                # Update the widget to show it's assigned
                widget_idx = self.selected_pending_idx
                if widget_idx < len(self.snippet_widgets):
                    widget = self.snippet_widgets[widget_idx]
                    color = pending['color']
                    widget.btn_header.setText(f"✓ Snippet {widget_idx + 1}")
                    widget.btn_header.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {color}; 
                            color: white; 
                            padding: 8px;
                            border: 2px solid #2ecc71;
                            border-radius: 4px;
                            text-align: left;
                            font-weight: bold;
                        }}
                        QPushButton:hover {{ border: 2px solid #fff; }}
                    """)
                    # Reconnect signals to use canvas index
                    widget.clicked.disconnect()
                    widget.clicked.connect(lambda checked=False, ci=idx: self.canvas.select_snippet(ci))
                
                self.log_panel.log(f"Region assigned to Snippet {widget_idx + 1}")
                
                # Clear selection and disable snip mode
                self.selected_pending_idx = None
                self.btn_snip.setChecked(False)
                self.canvas.set_snip_mode(False)
                
                # Check if all snippets are assigned
                unassigned = [p for p in self.pending_snippets if not p['assigned']]
                if unassigned:
                    self.log_panel.log(f"{len(unassigned)} snippets still need regions.")
                else:
                    self.log_panel.log("All snippets assigned! Ready to generate video.")
                return
        
        # Normal flow: create a new snippet widget (for non-JSON workflow)
        color = self.canvas.snippets[idx]['color']
        color_hex = color.name()
        
        widget = SnippetItemWidget(idx, color_hex, text="")
        widget.clicked.connect(self.on_snippet_click)
        widget.deleted.connect(self.on_snippet_delete)
        widget.text_changed.connect(self.on_script_changed)
        
        self.snippets_layout.addWidget(widget)
        self.snippet_widgets.append(widget)
        
        self.log_panel.log(f"Snippet {idx+1} created. Click to add script.")
        self.canvas.snippets[idx]['text'] = ""

    def on_script_changed(self, idx, text):
        """Handle script text changes."""
        if 0 <= idx < len(self.canvas.snippets):
            self.canvas.snippets[idx]['text'] = text
        # No need to log every keystroke
    
    def on_snippet_click(self, idx):
        """Select a snippet on the canvas."""
        self.canvas.select_snippet(idx)
    
    def on_snippet_delete(self, idx):
        """Delete a snippet."""
        if 0 <= idx < len(self.snippet_widgets):
            # Remove widget
            widget = self.snippet_widgets.pop(idx)
            self.snippets_layout.removeWidget(widget)
            widget.deleteLater()
            
            # Delete from canvas (this also shifts snippet indices in canvas)
            self.canvas.delete_snippet(idx)
            
            # Update remaining widgets
            self._refresh_snippet_widgets()
            
    def _refresh_snippet_widgets(self):
        """Refresh snippet widget indices after deletion."""
        for i, widget in enumerate(self.snippet_widgets):
            widget.update_index(i)
            # Reconnect signals with new index to capture correct closure
            # Actually, signals might need re-binding, but since we bind 'idx' at emit time in widget...
            # Wait, SnippetItemWidget emits 'idx' which is stored in the widget instance.
            # We updated 'idx' in widget.update_index(i), so the emitted signal will carry the new index.
            # We don't need to disconnect/reconnect here if the widget emits its own CURRENT index.
            pass

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
                'height': rect.height(),
                'text': snippet.get('text', '') # Pass text
            })
        
        # Show video options dialog
        options_dialog = VideoOptionsDialog(self)
        if options_dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        options = options_dialog.get_options()
        show_boxes = options['show_boxes']
        ken_burns = options['ken_burns']
        
        # Log selected options
        self.log_panel.log(f"Options: Ken Burns={'Enabled' if ken_burns else 'Disabled'}, Box Overlay={'Enabled' if show_boxes else 'Disabled'}")
        
        # Disable button during generation
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Generating...")
        
        # Get selected voice
        voice = self.selected_voice
        
        # Start worker thread
        self.video_worker = VideoGeneratorWorker(
            self.current_image_path,
            snippets_data,
            output_path,
            self.ratio_name,
            self.tts_handler,
            voice,
            show_boxes,
            ken_burns
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

