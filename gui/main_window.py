import os
import shutil
import json
from datetime import datetime
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QTextEdit, QComboBox, QFileDialog,
                             QScrollArea, QFrame, QMessageBox, QMenuBar, QMenu, QAction,
                             QActionGroup, QToolBar, QDialog, QApplication)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from gui.custom_widgets import LogPanel, ImageCanvas, SnippetItemWidget
from gui.dialogs import AspectRatioDialog, VideoOptionsDialog
from generation.video_generator import generate_video_from_snippets
from audio.tts_handler import TTSHandler
from gui.theme import SettingsStore, AppSettings, ThemeName, apply_theme

class VideoGeneratorWorker(QThread):
    """Background thread for video generation."""
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    
    def __init__(self, image_path, snippets, output_path, aspect_ratio, tts_handler, voice="en-US-AriaNeural", show_boxes=False, ken_burns=True, sub_images=None):
        super().__init__()
        self.image_path = image_path
        self.snippets = snippets
        self.output_path = output_path
        self.aspect_ratio = aspect_ratio
        self.tts_handler = tts_handler
        self.voice = voice
        self.show_boxes = show_boxes
        self.ken_burns = ken_burns
        self.sub_images = sub_images or []
    
    def run(self):
        # Step 1: Generate Audio for snippets
        self.progress.emit("Step 1/3: Generating Snippet Audio...")
        
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
        
        # Step 2: Generate Audio for sub-images
        sub_images_with_audio = []
        if self.sub_images:
            self.progress.emit("Step 2/3: Generating Sub-Image Audio...")
            for i, sub_img in enumerate(self.sub_images):
                sub_img_copy = sub_img.copy()
                text = sub_img.get('text', '').strip()
                
                if text:
                    self.progress.emit(f"Generating audio for {sub_img['id']}...")
                    audio_filename = f"subimg_{i}_{datetime.now().strftime('%H%M%S')}.mp3"
                    audio_path = os.path.join(audio_dir, audio_filename)
                    
                    success, duration = self.tts_handler.generate_audio(text, self.voice, audio_path)
                    
                    if success:
                        sub_img_copy['audio_path'] = audio_path
                        sub_img_copy['audio_duration'] = duration
                    else:
                        self.progress.emit(f"Failed to generate audio for {sub_img['id']}")
                        sub_img_copy['audio_path'] = None
                        sub_img_copy['audio_duration'] = 0.0
                else:
                    sub_img_copy['audio_path'] = None
                    sub_img_copy['audio_duration'] = 0.0
                
                sub_images_with_audio.append(sub_img_copy)

        # Step 3: Generate Video
        self.progress.emit("Step 3/3: Generating Video...")
        success, message = generate_video_from_snippets(
            self.image_path,
            snippets_with_audio,
            self.output_path,
            self.aspect_ratio,
            self.show_boxes,
            self.ken_burns,
            progress_callback=lambda msg: self.progress.emit(msg),
            sub_images=sub_images_with_audio
        )
        
        # Cleanup temp audio
        # shutil.rmtree(audio_dir, ignore_errors=True) # Keep for debugging or cleanup later
        
        self.finished.emit(success, message)


class MainWindow(QMainWindow):
    def __init__(self, ratio_name, settings_store: SettingsStore, initial_theme: ThemeName = "dark"):
        super().__init__()
        self.setWindowTitle("VideoForge - Professional Video Generator")
        self.resize(1400, 900)
        self.ratio_name = ratio_name  # Store for video generation
        self.settings_store = settings_store
        self.current_theme: ThemeName = initial_theme
        self.current_image_path = None  # Track current image
        self.video_worker = None  # Video generation thread
        self.tts_handler = TTSHandler()
        self.snippet_widgets = []  # replacing self.snippet_buttons
        self.pending_snippets = []  # Queue of imported but unassigned snippets
        self.selected_pending_idx = None  # Currently selected pending snippet awaiting region
        self.sub_images = []  # List of overlay sub-images
        self.sub_image_mode = False  # True when positioning a sub-image
        self.current_sub_image = None  # Currently being placed sub-image
        
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
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_container.setStyleSheet("""
            QWidget {
                background-color: #f3f3f3;
                border-right: 1px solid #e1e1e1;
            }
        """)
        
        # Log header
        log_header = QLabel("Activity Log")
        log_header.setStyleSheet("""
            QLabel {
                background-color: #ffffff;
                color: #202020;
                font-size: 14px;
                font-weight: 600;
                padding: 14px 20px;
                border-bottom: 1px solid #e1e1e1;
            }
        """)
        left_layout.addWidget(log_header)
        
        self.log_panel = LogPanel()
        left_layout.addWidget(self.log_panel)
        self.log_panel.log(f"VideoForge initialized. Aspect ratio: {ratio_name}")
        
        # --- 2. Center Panel: Image Canvas ---
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_container.setStyleSheet("""
            QWidget {
                background-color: #fafafa;
            }
        """)
        
        self.canvas = ImageCanvas(ratio_name)
        # Connect canvas signals
        self.canvas.log_signal.connect(self.log_panel.log)
        self.canvas.file_dropped_signal.connect(self.process_image_upload)
        
        center_layout.addWidget(self.canvas)
        
        # Control toolbar
        toolbar_container = QWidget()
        toolbar_container.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-bottom: 1px solid #e1e1e1;
            }
        """)
        toolbar_layout = QVBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(20, 14, 20, 14)
        toolbar_layout.setSpacing(12)
        
        # Primary actions row
        primary_row = QHBoxLayout()
        primary_row.setSpacing(8)
        
        btn_upload = QPushButton("Upload Image")
        btn_upload.setCursor(Qt.PointingHandCursor)
        btn_upload.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                border: none;
                font-size: 13px;
                font-weight: 400;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """)
        btn_upload.clicked.connect(self.open_upload_dialog)
        primary_row.addWidget(btn_upload)
        
        self.btn_snip = QPushButton("Create Region")
        self.btn_snip.setCheckable(True)
        self.btn_snip.setCursor(Qt.PointingHandCursor)
        self.btn_snip.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #202020;
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #d1d1d1;
                font-size: 13px;
                font-weight: 400;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border-color: #b1b1b1;
            }
            QPushButton:checked {
                background-color: #0078d4;
                color: white;
                border-color: #0078d4;
            }
        """)
        self.btn_snip.clicked.connect(self.toggle_snip_mode)
        primary_row.addWidget(self.btn_snip)
        
        primary_row.addStretch()
        toolbar_layout.addLayout(primary_row)
        
        # Secondary actions row
        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(8)
        
        self.btn_add_subimage = QPushButton("Add Overlay")
        self.btn_add_subimage.setCursor(Qt.PointingHandCursor)
        self.btn_add_subimage.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #202020;
                padding: 6px 14px;
                border-radius: 4px;
                border: 1px solid #d1d1d1;
                font-size: 12px;
                font-weight: 400;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border-color: #b1b1b1;
            }
        """)
        self.btn_add_subimage.clicked.connect(self.add_sub_image)
        secondary_row.addWidget(self.btn_add_subimage)
        
        self.btn_place_subimage = QPushButton("Place Overlay")
        self.btn_place_subimage.setCursor(Qt.PointingHandCursor)
        self.btn_place_subimage.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #202020;
                padding: 6px 14px;
                border-radius: 4px;
                border: 1px solid #d1d1d1;
                font-size: 12px;
                font-weight: 400;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border-color: #b1b1b1;
            }
            QPushButton:disabled {
                background-color: #f3f3f3;
                color: #a1a1a1;
                border-color: #e1e1e1;
            }
        """)
        self.btn_place_subimage.setEnabled(False)
        self.btn_place_subimage.clicked.connect(self.place_sub_image)
        secondary_row.addWidget(self.btn_place_subimage)
        
        secondary_row.addStretch()
        
        # Zoom controls
        zoom_group = QHBoxLayout()
        zoom_group.setSpacing(6)
        
        btn_zoom_out = QPushButton("−")
        btn_zoom_out.setFixedSize(32, 32)
        btn_zoom_out.setCursor(Qt.PointingHandCursor)
        btn_zoom_out.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #202020;
                font-size: 16px;
                font-weight: 400;
                border-radius: 4px;
                border: 1px solid #d1d1d1;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border-color: #b1b1b1;
            }
        """)
        btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        zoom_group.addWidget(btn_zoom_out)
        
        btn_reset_zoom = QPushButton("Reset")
        btn_reset_zoom.setCursor(Qt.PointingHandCursor)
        btn_reset_zoom.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #202020;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid #d1d1d1;
                font-size: 12px;
                font-weight: 400;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border-color: #b1b1b1;
            }
        """)
        btn_reset_zoom.clicked.connect(self.canvas.reset_zoom)
        zoom_group.addWidget(btn_reset_zoom)
        
        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(32, 32)
        btn_zoom_in.setCursor(Qt.PointingHandCursor)
        btn_zoom_in.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #202020;
                font-size: 16px;
                font-weight: 400;
                border-radius: 4px;
                border: 1px solid #d1d1d1;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border-color: #b1b1b1;
            }
        """)
        btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        zoom_group.addWidget(btn_zoom_in)
        
        secondary_row.addLayout(zoom_group)
        toolbar_layout.addLayout(secondary_row)
        
        center_layout.addWidget(toolbar_container)

        
        # --- 3. Right Panel: Storyboard ---
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_container.setStyleSheet("""
            QWidget {
                background-color: #f3f3f3;
                border-left: 1px solid #e1e1e1;
            }
        """)
        
        # Header section
        header_section = QWidget()
        header_section.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-bottom: 1px solid #e1e1e1;
            }
        """)
        header_layout = QVBoxLayout(header_section)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(12)
        
        # Main title
        lbl_title = QLabel("Storyboard")
        lbl_title.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: 600;
                color: #202020;
                padding: 0;
            }
        """)
        header_layout.addWidget(lbl_title)
        
        # Scenes section header
        scenes_header = QHBoxLayout()
        scenes_header.setContentsMargins(0, 0, 0, 0)
        
        lbl_snippets = QLabel("SCENES")
        lbl_snippets.setStyleSheet("""
            QLabel {
                font-size: 11px;
                font-weight: 600;
                color: #666666;
                letter-spacing: 0.5px;
            }
        """)
        scenes_header.addWidget(lbl_snippets)
        scenes_header.addStretch()
        
        # Snippet count badge
        self.lbl_snippet_count = QLabel("0")
        self.lbl_snippet_count.setFixedSize(24, 24)
        self.lbl_snippet_count.setAlignment(Qt.AlignCenter)
        self.lbl_snippet_count.setStyleSheet("""
            QLabel {
                background-color: #0078d4;
                color: white;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        scenes_header.addWidget(self.lbl_snippet_count)
        
        header_layout.addLayout(scenes_header)
        right_layout.addWidget(header_section)
        
        # Scrollable container for snippets
        snippets_scroll = QScrollArea()
        snippets_scroll.setWidgetResizable(True)
        snippets_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        snippets_scroll.setFrameShape(QFrame.NoFrame)
        snippets_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #f3f3f3;
                width: 12px;
                border-radius: 0px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background-color: #c1c1c1;
                border-radius: 6px;
                min-height: 30px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a1a1a1;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
                border: none;
            }
        """)
        
        self.snippets_container = QWidget()
        self.snippets_container.setStyleSheet("background-color: transparent;")
        self.snippets_layout = QVBoxLayout(self.snippets_container)
        self.snippets_layout.setContentsMargins(16, 16, 16, 16)
        self.snippets_layout.setSpacing(12)
        self.snippets_layout.addStretch()
        
        snippets_scroll.setWidget(self.snippets_container)
        right_layout.addWidget(snippets_scroll, 1)
        
        # Connect canvas signals
        self.canvas.snippet_created.connect(self.on_snippet_created)
        self.snippet_buttons = []  # Track buttons
        
        # Generate Button container
        generate_container = QWidget()
        generate_container.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-top: 1px solid #e1e1e1;
            }
        """)
        generate_layout = QVBoxLayout(generate_container)
        generate_layout.setContentsMargins(20, 16, 20, 16)
        
        self.btn_generate = QPushButton("Generate Video")
        self.btn_generate.setFixedHeight(44)
        self.btn_generate.setCursor(Qt.PointingHandCursor)
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-size: 14px;
                font-weight: 400;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #e1e1e1;
                color: #a1a1a1;
            }
        """)
        self.btn_generate.clicked.connect(self.generate_video)
        generate_layout.addWidget(self.btn_generate)
        
        right_layout.addWidget(generate_container)
        
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
                background-color: #ffffff;
                color: #202020;
                padding: 2px;
                font-size: 13px;
                border-bottom: 1px solid #e1e1e1;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 6px 12px;
                border-radius: 2px;
            }
            QMenuBar::item:selected {
                background-color: #e8f4f8;
            }
            QMenu {
                background-color: #ffffff;
                color: #202020;
                border: 1px solid #d1d1d1;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 32px 6px 16px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: white;
            }
            QMenu::indicator {
                width: 16px;
                height: 16px;
                margin-left: 5px;
            }
            QMenu::indicator:checked {
                image: none;
                background-color: #0078d4;
                border-radius: 2px;
            }
        """)
        
        # Voice Menu
        voice_menu = menubar.addMenu("Voice")
        
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
        files_menu = menubar.addMenu("File")
        
        upload_json_action = QAction("Import JSON", self)
        upload_json_action.triggered.connect(self._on_upload_json)
        files_menu.addAction(upload_json_action)

        # View Menu (Theme)
        view_menu = menubar.addMenu("View")
        theme_menu = view_menu.addMenu("Theme")

        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)

        action_dark = QAction("Dark", self)
        action_dark.setCheckable(True)
        action_dark.setChecked(self.current_theme == "dark")
        action_dark.triggered.connect(lambda checked: self._set_theme("dark"))
        self.theme_action_group.addAction(action_dark)
        theme_menu.addAction(action_dark)

        action_light = QAction("Light", self)
        action_light.setCheckable(True)
        action_light.setChecked(self.current_theme == "light")
        action_light.triggered.connect(lambda checked: self._set_theme("light"))
        self.theme_action_group.addAction(action_light)
        theme_menu.addAction(action_light)

    def _set_theme(self, theme: ThemeName):
        if theme == self.current_theme:
            return
        self.current_theme = theme
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)
        # Persist
        self.settings_store.save(AppSettings(theme=theme))
        self.log_panel.log(f"Theme set to: {theme}")
    
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
                    widget.lbl_title.setText(f"Snippet {i+1}")
                    widget.lbl_preview.setText("Click to assign region")
                    
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
                        # Highlight selected
                        widget.setStyleSheet("""
                            SnippetItemWidget {
                                background-color: #252525;
                                border-radius: 8px;
                                border: 2px solid #5a9bd6;
                            }
                        """)
                    elif i < len(self.pending_snippets) and not self.pending_snippets[i]['assigned']:
                        # Reset non-selected
                        widget.setStyleSheet("""
                            SnippetItemWidget {
                                background-color: #252525;
                                border-radius: 8px;
                                border: 1px solid #3a3a3a;
                            }
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

    def add_sub_image(self):
        """Open file dialog to add a sub-image overlay."""
        if not self.current_image_path:
            self.log_panel.log("Error: Please upload a main image first.")
            QMessageBox.warning(self, "No Image", "Please upload a main image first.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Sub-Image", 
            "", 
            "Images (*.png *.jpg *.jpeg *.gif *.bmp)"
        )
        if file_path:
            # Create sub-image data
            sub_image_id = f"sub-image-{len(self.sub_images) + 1}"
            self.current_sub_image = {
                'id': sub_image_id,
                'image_path': file_path,
                'position': (50, 50),  # Default position
                'size': None,  # Will be set from actual image
                'after_snip': len(self.canvas.snippets) - 1 if self.canvas.snippets else 0,
                'text': '',
                'audio_path': None,
                'audio_duration': 0.0,
                'persistent': False
            }
            
            # Enable sub-image mode on canvas
            self.sub_image_mode = True
            self.canvas.set_sub_image(file_path)
            self.btn_place_subimage.setEnabled(True)
            self.btn_snip.setEnabled(False)  # Disable snip while placing
            
            self.log_panel.log(f"Loaded {sub_image_id}. Drag to position, then click 'Place Sub-Image'.")
    
    def place_sub_image(self):
        """Capture current sub-image position and add to list."""
        if not self.current_sub_image or not self.sub_image_mode:
            return
        
        # Get position from canvas
        pos = self.canvas.get_sub_image_position()
        size = self.canvas.get_sub_image_source_size()  # Get actual pixel size for compositing
        
        if pos and size:
            self.current_sub_image['position'] = pos
            self.current_sub_image['size'] = size  # Size in pixels for compositing
            
            # Add to sub_images list
            self.sub_images.append(self.current_sub_image)
            
            # Create SubImageWidget in storyboard
            self._create_sub_image_widget(self.current_sub_image)
            
            self.log_panel.log(f"Placed {self.current_sub_image['id']} at ({pos[0]}, {pos[1]}) size {size[0]}x{size[1]}")
            
            # Reset state
            self.current_sub_image = None
            self.sub_image_mode = False
            self.canvas.clear_sub_image()
            self.btn_place_subimage.setEnabled(False)
            self.btn_snip.setEnabled(True)
    
    def _create_sub_image_widget(self, sub_image):
        """Create a widget for the sub-image in the storyboard."""
        from gui.custom_widgets import SubImageWidget
        
        widget = SubImageWidget(
            sub_image['id'],
            sub_image['image_path'],
            len(self.canvas.snippets),  # Total snips for dropdown
            sub_image['after_snip']
        )
        widget.deleted.connect(lambda sid=sub_image['id']: self._delete_sub_image(sid))
        widget.settings_changed.connect(self._on_sub_image_settings_changed)
        
        self.snippets_layout.addWidget(widget)
        self.log_panel.log(f"Added {sub_image['id']} to storyboard")
    
    def _delete_sub_image(self, sub_image_id):
        """Delete a sub-image by ID."""
        self.sub_images = [s for s in self.sub_images if s['id'] != sub_image_id]
        self.log_panel.log(f"Deleted {sub_image_id}")
    
    def _on_sub_image_settings_changed(self, sub_image_id, settings):
        """Handle sub-image settings changes from widget."""
        for sub_img in self.sub_images:
            if sub_img['id'] == sub_image_id:
                sub_img.update(settings)
                break

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
                    widget.lbl_title.setText(f"Snippet {widget_idx + 1}")
                    widget.set_assigned_style(True)
                    widget.lbl_preview.setText(pending['text'][:50] + "..." if len(pending['text']) > 50 else pending['text'])
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
            ken_burns,
            self.sub_images  # Pass sub-images
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

