from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTextEdit, 
                             QFileDialog, QFrame, QSizePolicy, QGesture,
                             QPinchGesture, QPushButton, QHBoxLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QEvent, QPointF
from PyQt5.QtGui import QPainter, QPixmap, QColor, QPen, QImage
from datetime import datetime

class LogPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_title = QLabel("Activity Logs")
        lbl_title.setStyleSheet("font-weight: bold; color: #ccc; margin-bottom: 5px;")
        layout.addWidget(lbl_title)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                font-family: Consolas, Monaco, monospace;
                font-size: 11px;
                border: 1px solid #333;
            }
        """)
        layout.addWidget(self.text_edit)
        
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.text_edit.append(f"[{timestamp}] {message}")
        self.text_edit.verticalScrollBar().setValue(
            self.text_edit.verticalScrollBar().maximum()
        )

class ImageCanvas(QWidget):
    log_signal = pyqtSignal(str)
    file_dropped_signal = pyqtSignal(str)
    snippet_created = pyqtSignal(int, dict)  # (index, {x, y, w, h} in source coords)
    snippet_deleted = pyqtSignal(int)  # index
    
    def __init__(self, ratio_name):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) # Fix: Expand to fill
        self.ratio_name = ratio_name
        self.setMouseTracking(True)
        self.setAcceptDrops(True) # Enable Drop
        
        # Enable touch and gesture support
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self.grabGesture(Qt.PinchGesture)
        
        self.source_pixmap = None 
        self.scaled_pixmap = None
        self.image_pos = QPoint(0, 0)
        self.last_mouse_pos = QPoint()
        self.is_dragging = False
        self.scale_factor = 1.0
        
        # Zoom state
        self.zoom_level = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 5.0
        self.zoom_center = QPointF(0, 0)  # For pinch zoom centering
        
        # Snippet state
        self.snip_mode = False
        self.snippets = []  # List of dicts: {source_rect: QRect, color: QColor}
        self.current_snippet_rect = None  # QRect being drawn (screen coords)
        self.snippet_start_pos = None  # Starting point for drawing
        self.selected_snippet_idx = -1  # -1 = none selected
        self.snippet_colors = [
            QColor("#FF6B6B"), QColor("#4ECDC4"), QColor("#45B7D1"),
            QColor("#96CEB4"), QColor("#FFEAA7"), QColor("#DDA0DD"),
            QColor("#98D8C8"), QColor("#F7DC6F"), QColor("#BB8FCE")
        ]
        
        # Sub-image overlay state
        self.sub_image_pixmap = None  # QPixmap of overlay image
        self.sub_image_pos = QPoint(50, 50)  # Position on canvas (screen coords)
        self.sub_image_source_pos = (0, 0)  # Position on source image
        self.sub_image_dragging = False  # True when dragging sub-image
        self.sub_image_size = None  # (width, height) of sub-image
        
        # Determine aspect ratio float
        if "9:16" in ratio_name:
            self.aspect_ratio = 9/16
        elif "16:9" in ratio_name:
            self.aspect_ratio = 16/9
        else:
            self.aspect_ratio = 1.0
            
        self.viewport_rect = QRect()


    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
            
    def dropEvent(self, event):
        # Handle file drop
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            # Check extensions roughly
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                self.file_dropped_signal.emit(f)
                return # Take first valid image

    # ========== Gesture & Zoom Methods ==========
    
    def event(self, event):
        """Override to catch gesture events."""
        if event.type() == QEvent.Gesture:
            return self.gestureEvent(event)
        return super().event(event)
    
    def gestureEvent(self, event):
        """Handle pinch gesture for zoom."""
        pinch = event.gesture(Qt.PinchGesture)
        if pinch:
            if pinch.state() == Qt.GestureStarted:
                self.zoom_center = pinch.centerPoint()
            
            scale_factor = pinch.scaleFactor()
            if scale_factor != 1.0:
                self._apply_zoom(scale_factor, pinch.centerPoint())
        return True
    
    def wheelEvent(self, event):
        """Mouse wheel zoom - scroll up to zoom in, scroll down to zoom out."""
        if not self.source_pixmap:
            return
            
        # Only zoom if cursor is in viewport
        if not self.viewport_rect.contains(event.pos()):
            return
        
        # Calculate zoom factor from wheel delta
        delta = event.angleDelta().y()
        if delta > 0:
            factor = 1.1  # Zoom in
        else:
            factor = 0.9  # Zoom out
        
        self._apply_zoom(factor, QPointF(event.pos()))
    
    def _apply_zoom(self, factor, center_point):
        """Apply zoom with given factor, centered on a point."""
        old_zoom = self.zoom_level
        new_zoom = self.zoom_level * factor
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
        
        if new_zoom == old_zoom:
            return
        
        self.zoom_level = new_zoom
        
        # Adjust image position to keep zoom centered on cursor/pinch point
        # This is done by adjusting the image offset proportionally
        if self.viewport_rect.contains(center_point.toPoint()):
            # Relative position of center in viewport
            rel_x = center_point.x() - self.viewport_rect.center().x()
            rel_y = center_point.y() - self.viewport_rect.center().y()
            
            # Adjust image position
            zoom_change = new_zoom / old_zoom
            self.image_pos = QPoint(
                int(self.image_pos.x() * zoom_change - rel_x * (zoom_change - 1)),
                int(self.image_pos.y() * zoom_change - rel_y * (zoom_change - 1))
            )
        
        self._log_zoom_coordinates()
        self.update()
    
    def zoom_in(self):
        """Zoom in by 20%, centered on viewport."""
        self._apply_zoom(1.2, QPointF(self.viewport_rect.center()))
    
    def zoom_out(self):
        """Zoom out by 20%, centered on viewport."""
        self._apply_zoom(0.8, QPointF(self.viewport_rect.center()))
    
    def reset_zoom(self):
        """Reset zoom to 1.0x and center the image."""
        self.zoom_level = 1.0
        self.image_pos = QPoint(0, 0)
        self._log_zoom_coordinates()
        self.update()
    
    def _log_zoom_coordinates(self):
        """Log detailed zoom and coordinate information."""
        if not self.source_pixmap:
            return
            
        src_w = self.source_pixmap.width()
        src_h = self.source_pixmap.height()
        vp_w = self.viewport_rect.width()
        vp_h = self.viewport_rect.height()
        
        # Calculate effective scale (base scale * zoom)
        base_scale_w = vp_w / src_w
        base_scale_h = vp_h / src_h
        base_scale = max(base_scale_w, base_scale_h)
        effective_scale = base_scale * self.zoom_level
        
        # Drawn image dimensions
        dw = src_w * effective_scale
        dh = src_h * effective_scale
        
        # Calculate visible region in source image coords
        screen_crop_x = (dw - vp_w) / 2 - self.image_pos.x()
        screen_crop_y = (dh - vp_h) / 2 - self.image_pos.y()
        
        source_crop_x = max(0, int(screen_crop_x / effective_scale))
        source_crop_y = max(0, int(screen_crop_y / effective_scale))
        source_crop_w = int(vp_w / effective_scale)
        source_crop_h = int(vp_h / effective_scale)
        
        # Clamp to image bounds
        source_crop_x = min(source_crop_x, src_w)
        source_crop_y = min(source_crop_y, src_h)
        
        self.log_signal.emit(
            f"Zoom: {self.zoom_level:.2f}x | "
            f"Visible Region: ({source_crop_x}, {source_crop_y}) "
            f"to ({source_crop_x + source_crop_w}, {source_crop_y + source_crop_h}) | "
            f"Image: {src_w}x{src_h} | Viewport: {vp_w}x{vp_h}"
        )


    def set_image(self, image_path):
        self.source_pixmap = QPixmap(image_path)
        self.log_signal.emit(f"Image loaded: {image_path} ({self.source_pixmap.width()}x{self.source_pixmap.height()})")
        # Reset state forcing re-calculation in paintEvent
        self.scaled_pixmap = None
        self.image_pos = QPoint(0, 0)
        self.zoom_level = 1.0  # Reset zoom on new image
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # 1. Draw Background
        painter.fillRect(self.rect(), QColor("#121212"))
        
        # 2. Calculate Viewport (Canvas) Size & Position
        w = self.width() - 40 # Margin
        h = self.height() - 40
        
        if w / h > self.aspect_ratio:
            vp_h = h
            vp_w = int(vp_h * self.aspect_ratio)
        else:
            vp_w = w
            vp_h = int(vp_w / self.aspect_ratio)
            
        vp_x = (self.width() - vp_w) // 2
        vp_y = (self.height() - vp_h) // 2
        
        self.viewport_rect = QRect(vp_x, vp_y, vp_w, vp_h)
        
        # 3. Draw Viewport Background
        painter.fillRect(self.viewport_rect, QColor("black"))
        
        # 4. Draw Image (Aspect Fill / Cover)
        if self.source_pixmap:
            # Calculate Scale IF needed (only if viewport changed or new image)
            # We want 'Aspect Fill': Scale so the Smaller dimension fits the Viewport's dimension
            # causing the larger dimension to overflow (clip)
            
            src_w = self.source_pixmap.width()
            src_h = self.source_pixmap.height()
            
            # Scale to cover the viewport
            scale_w = self.viewport_rect.width() / src_w
            scale_h = self.viewport_rect.height() / src_h
            base_scale = max(scale_w, scale_h) # 'Cover' mode
            self.scale_factor = base_scale * self.zoom_level  # Apply zoom
            
            # Create scaled pixmap for drawing (efficient?) 
            # Or just use transform. For massive images, pre-scaling is better for performance.
            # But let's use dynamic drawing for smoothness during resize.
            
            # Draw Width/Height
            dw = int(src_w * self.scale_factor)
            dh = int(src_h * self.scale_factor)
            
            # Center alignment logic
            # image_pos (0,0) means center of image is at center of viewport
            # Top-Left of image relative to Viewport Top-Left:
            
            # Center of Viewport
            vp_cx = self.viewport_rect.width() / 2
            vp_cy = self.viewport_rect.height() / 2
            
            # Top-Left of drawn image
            draw_x = vp_cx - (dw / 2) + self.image_pos.x()
            draw_y = vp_cy - (dh / 2) + self.image_pos.y()
            
            painter.save()
            painter.setClipRect(self.viewport_rect)
            
            # We draw the source pixmap scaled
            # Using drawPixmap with target rect scales it
            target_rect = QRect(int(self.viewport_rect.x() + draw_x), 
                                int(self.viewport_rect.y() + draw_y), 
                                dw, dh)
            painter.drawPixmap(target_rect, self.source_pixmap)
            
            # Draw snippets
            for i, snippet in enumerate(self.snippets):
                screen_rect = self._source_to_screen_rect(snippet['source_rect'])
                if screen_rect:
                    color = snippet['color']
                    # Only show if selected or currently drawing
                    if i == self.selected_snippet_idx:
                        # Selected: solid border, semi-transparent fill
                        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 50))
                        pen = QPen(color, 3)
                        painter.setPen(pen)
                        painter.drawRect(screen_rect)
                    else:
                        # Not selected: invisible (or very faint)
                        pass
            
            # Draw current snippet being created
            if self.current_snippet_rect and self.snip_mode:
                color = self.snippet_colors[len(self.snippets) % len(self.snippet_colors)]
                painter.setBrush(QColor(color.red(), color.green(), color.blue(), 80))
                pen = QPen(color, 2, Qt.DashLine)
                painter.setPen(pen)
                painter.drawRect(self.current_snippet_rect)
            
            # Draw sub-image overlay if active
            if self.sub_image_pixmap:
                # Draw semi-transparent background
                painter.setOpacity(0.9)
                painter.drawPixmap(self.sub_image_pos, self.sub_image_pixmap)
                painter.setOpacity(1.0)
                
                # Draw border around sub-image
                sub_rect = QRect(
                    self.sub_image_pos.x(),
                    self.sub_image_pos.y(),
                    self.sub_image_pixmap.width(),
                    self.sub_image_pixmap.height()
                )
                pen = QPen(QColor("#2ecc71"), 3, Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(sub_rect)
                
                # Draw drag handle hint
                painter.setPen(QColor("#fff"))
                painter.drawText(sub_rect.center().x() - 30, sub_rect.bottom() + 15, "Drag to position")
            
            painter.restore()
        
        # 5. Draw Viewport Border
        pen = QPen(QColor("#5a9bd6"), 2)
        painter.setPen(pen)
        painter.drawRect(self.viewport_rect)
        
    def mousePressEvent(self, event):
        if not self.source_pixmap or not self.viewport_rect.contains(event.pos()):
            return
        
        # Check if clicking on sub-image overlay for dragging
        if self.sub_image_pixmap:
            sub_rect = QRect(
                self.sub_image_pos.x(),
                self.sub_image_pos.y(),
                self.sub_image_pixmap.width(),
                self.sub_image_pixmap.height()
            )
            if sub_rect.contains(event.pos()):
                self.sub_image_dragging = True
                self.last_mouse_pos = event.pos()
                self.setCursor(Qt.SizeAllCursor)
                return
            
        if self.snip_mode:
            # Start drawing snippet
            self.snippet_start_pos = event.pos()
            self.current_snippet_rect = QRect(event.pos(), event.pos())
            self.setCursor(Qt.CrossCursor)
        else:
            # Pan mode
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            
    def mouseMoveEvent(self, event):
        # Handle sub-image dragging first
        if self.sub_image_dragging and self.sub_image_pixmap:
            delta = event.pos() - self.last_mouse_pos
            self.sub_image_pos += delta
            self.last_mouse_pos = event.pos()
            self.update()
            return
        
        if self.snip_mode and self.snippet_start_pos:
            # Update snippet rectangle
            self.current_snippet_rect = QRect(
                self.snippet_start_pos,
                event.pos()
            ).normalized()
            self.update()
        elif self.is_dragging and self.source_pixmap:
            delta = event.pos() - self.last_mouse_pos
            self.image_pos += delta
            self.last_mouse_pos = event.pos()
            
            # Log crop coordinates
            src_w = self.source_pixmap.width()
            src_h = self.source_pixmap.height()
            dw = src_w * self.scale_factor
            dh = src_h * self.scale_factor
            vp_w = self.viewport_rect.width()
            vp_h = self.viewport_rect.height()
            
            screen_crop_x = (dw - vp_w)/2 - self.image_pos.x()
            screen_crop_y = (dh - vp_h)/2 - self.image_pos.y()
            
            source_crop_x = int(screen_crop_x / self.scale_factor)
            source_crop_y = int(screen_crop_y / self.scale_factor)
            source_crop_w = int(vp_w / self.scale_factor)
            source_crop_h = int(vp_h / self.scale_factor)
            
            self.log_signal.emit(f"Crop Rect: x={source_crop_x}, y={source_crop_y}, w={source_crop_w}, h={source_crop_h}")
            self.update()
            
    def mouseReleaseEvent(self, event):
        if self.snip_mode and self.snippet_start_pos and self.current_snippet_rect:
            # Save the snippet
            if self.current_snippet_rect.width() > 10 and self.current_snippet_rect.height() > 10:
                source_rect = self._screen_to_source_rect(self.current_snippet_rect)
                if source_rect:
                    color = self.snippet_colors[len(self.snippets) % len(self.snippet_colors)]
                    snippet = {
                        'source_rect': source_rect,
                        'color': color
                    }
                    self.snippets.append(snippet)
                    idx = len(self.snippets) - 1
                    
                    self.log_signal.emit(
                        f"Snippet {idx + 1} created: x={source_rect.x()}, y={source_rect.y()}, "
                        f"w={source_rect.width()}, h={source_rect.height()}"
                    )
                    
                    # Emit signal with source coordinates
                    self.snippet_created.emit(idx, {
                        'x': source_rect.x(),
                        'y': source_rect.y(),
                        'w': source_rect.width(),
                        'h': source_rect.height()
                    })
                    
                    # Select the new snippet
                    self.selected_snippet_idx = idx
            
            self.current_snippet_rect = None
            self.snippet_start_pos = None
            self.update()
        elif self.is_dragging:
            self.is_dragging = False
        
        # Reset sub-image dragging
        if self.sub_image_dragging:
            self.sub_image_dragging = False
            
        self.setCursor(Qt.CrossCursor if self.snip_mode else Qt.ArrowCursor)

    # ========== Snippet Methods ==========
    
    def set_snip_mode(self, enabled):
        """Toggle snip mode for drawing snippets."""
        self.snip_mode = enabled
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        if enabled:
            self.log_signal.emit("Snip mode ON - Draw a rectangle to create a snippet")
        else:
            self.log_signal.emit("Snip mode OFF")
        self.update()
    
    def select_snippet(self, idx):
        """Select a snippet to highlight it."""
        if 0 <= idx < len(self.snippets):
            self.selected_snippet_idx = idx
            snippet = self.snippets[idx]
            self.log_signal.emit(
                f"Selected Snippet {idx + 1}: x={snippet['source_rect'].x()}, "
                f"y={snippet['source_rect'].y()}, w={snippet['source_rect'].width()}, "
                f"h={snippet['source_rect'].height()}"
            )
        else:
            self.selected_snippet_idx = -1
        self.update()
    
    def delete_snippet(self, idx):
        """Delete a snippet by index."""
        if 0 <= idx < len(self.snippets):
            self.snippets.pop(idx)
            self.log_signal.emit(f"Deleted Snippet {idx + 1}")
            self.snippet_deleted.emit(idx)
            if self.selected_snippet_idx == idx:
                self.selected_snippet_idx = -1
            elif self.selected_snippet_idx > idx:
                self.selected_snippet_idx -= 1
            self.update()
    
    def clear_snippets(self):
        """Clear all snippets."""
        self.snippets.clear()
        self.selected_snippet_idx = -1
        self.log_signal.emit("Cleared all snippets")
        self.update()
    
    def _screen_to_source_rect(self, screen_rect):
        """Convert screen rectangle to source image coordinates."""
        if not self.source_pixmap or not self.viewport_rect.isValid():
            return None
        
        src_w = self.source_pixmap.width()
        src_h = self.source_pixmap.height()
        dw = src_w * self.scale_factor
        dh = src_h * self.scale_factor
        
        vp_cx = self.viewport_rect.width() / 2
        vp_cy = self.viewport_rect.height() / 2
        
        # Image top-left in viewport coords
        img_x = vp_cx - (dw / 2) + self.image_pos.x() + self.viewport_rect.x()
        img_y = vp_cy - (dh / 2) + self.image_pos.y() + self.viewport_rect.y()
        
        # Convert screen rect to source coords
        source_x = int((screen_rect.x() - img_x) / self.scale_factor)
        source_y = int((screen_rect.y() - img_y) / self.scale_factor)
        source_w = int(screen_rect.width() / self.scale_factor)
        source_h = int(screen_rect.height() / self.scale_factor)
        
        # Clamp to source image bounds
        source_x = max(0, min(source_x, src_w))
        source_y = max(0, min(source_y, src_h))
        
        return QRect(source_x, source_y, source_w, source_h)
    
    def _source_to_screen_rect(self, source_rect):
        """Convert source image rectangle to screen coordinates."""
        if not self.source_pixmap or not self.viewport_rect.isValid():
            return None
        
        src_w = self.source_pixmap.width()
        src_h = self.source_pixmap.height()
        dw = src_w * self.scale_factor
        dh = src_h * self.scale_factor
        
        vp_cx = self.viewport_rect.width() / 2
        vp_cy = self.viewport_rect.height() / 2
        
        # Image top-left in screen coords
        img_x = vp_cx - (dw / 2) + self.image_pos.x() + self.viewport_rect.x()
        img_y = vp_cy - (dh / 2) + self.image_pos.y() + self.viewport_rect.y()
        
        # Convert source rect to screen coords
        screen_x = int(img_x + source_rect.x() * self.scale_factor)
        screen_y = int(img_y + source_rect.y() * self.scale_factor)
        screen_w = int(source_rect.width() * self.scale_factor)
        screen_h = int(source_rect.height() * self.scale_factor)
        
        return QRect(screen_x, screen_y, screen_w, screen_h)
    
    def set_sub_image(self, image_path):
        """Load and display a sub-image overlay for positioning."""
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        
        # Scale down if too large (max 200px on longest side for overlay)
        max_size = 200
        if pixmap.width() > max_size or pixmap.height() > max_size:
            pixmap = pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.sub_image_pixmap = pixmap
        self.sub_image_size = (pixmap.width(), pixmap.height())
        self.sub_image_pos = QPoint(
            self.viewport_rect.x() + 50,
            self.viewport_rect.y() + 50
        )
        self.update()
    
    def clear_sub_image(self):
        """Remove the sub-image overlay."""
        self.sub_image_pixmap = None
        self.sub_image_size = None
        self.sub_image_dragging = False
        self.update()
    
    def get_sub_image_position(self):
        """Get sub-image position in source image coordinates."""
        if not self.sub_image_pixmap or not self.source_pixmap:
            return None
        
        # Convert screen position to source image coordinates
        dw = int(self.source_pixmap.width() * self.scale_factor)
        dh = int(self.source_pixmap.height() * self.scale_factor)
        
        vp_cx = self.viewport_rect.width() / 2
        vp_cy = self.viewport_rect.height() / 2
        
        img_x = vp_cx - (dw / 2) + self.image_pos.x() + self.viewport_rect.x()
        img_y = vp_cy - (dh / 2) + self.image_pos.y() + self.viewport_rect.y()
        
        source_x = int((self.sub_image_pos.x() - img_x) / self.scale_factor)
        source_y = int((self.sub_image_pos.y() - img_y) / self.scale_factor)
        
        return (source_x, source_y)
    
    def get_sub_image_size(self):
        """Get sub-image display size."""
        return self.sub_image_size


class SnippetItemWidget(QWidget):
    """
    A modern snippet widget with smooth animations and better text handling.
    Contains a header button, status indicator, delete button, and expandable script text.
    """
    text_changed = pyqtSignal(int, str)  # idx, text
    clicked = pyqtSignal(int)            # idx
    deleted = pyqtSignal(int)            # idx
    
    def __init__(self, idx, color_hex, text=""):
        super().__init__()
        self.idx = idx
        self.color_hex = color_hex
        self.expanded = False
        self._target_height = 0
        
        # Main styling
        self.setStyleSheet(f"""
            SnippetItemWidget {{
                background-color: #252525;
                border-radius: 8px;
                border: 1px solid #3a3a3a;
            }}
            SnippetItemWidget:hover {{
                border: 1px solid #4a4a4a;
            }}
        """)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # --- Header Row ---
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        # Color indicator bar
        self.color_bar = QFrame()
        self.color_bar.setFixedSize(4, 36)
        self.color_bar.setStyleSheet(f"background-color: {color_hex}; border-radius: 2px;")
        header_layout.addWidget(self.color_bar)
        
        # Snippet info container
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        self.lbl_title = QLabel(f"Snippet {idx + 1}")
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #fff;")
        info_layout.addWidget(self.lbl_title)
        
        # Preview text (truncated)
        preview = text[:50] + "..." if len(text) > 50 else text if text else "No script yet"
        self.lbl_preview = QLabel(preview)
        self.lbl_preview.setStyleSheet("font-size: 11px; color: #888;")
        self.lbl_preview.setWordWrap(False)
        info_layout.addWidget(self.lbl_preview)
        
        header_layout.addLayout(info_layout, 1)
        
        # Expand button
        self.btn_expand = QPushButton("▼")
        self.btn_expand.setFixedSize(32, 32)
        self.btn_expand.setCursor(Qt.PointingHandCursor)
        self.btn_expand.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                color: #fff;
            }
        """)
        self.btn_expand.clicked.connect(self.toggle_expand)
        header_layout.addWidget(self.btn_expand)
        
        # Delete button
        self.btn_delete = QPushButton("×")
        self.btn_delete.setFixedSize(32, 32)
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                color: white;
                border-color: #d32f2f;
            }
        """)
        self.btn_delete.clicked.connect(lambda: self.deleted.emit(self.idx))
        header_layout.addWidget(self.btn_delete)
        
        layout.addWidget(header_widget)
        
        # Clickable header area
        self.btn_header = QPushButton()
        self.btn_header.setFixedHeight(0)
        self.btn_header.setVisible(False)
        self.btn_header.clicked.connect(self._on_header_click)
        
        # Make header clickable for selection
        header_widget.mousePressEvent = lambda e: self._on_header_click()
        header_widget.setCursor(Qt.PointingHandCursor)
        
        # --- Script Text Area (Expandable) ---
        self.txt_container = QWidget()
        self.txt_container.setMaximumHeight(0)
        txt_layout = QVBoxLayout(self.txt_container)
        txt_layout.setContentsMargins(0, 0, 0, 0)
        
        self.txt_script = QTextEdit()
        self.txt_script.setPlaceholderText("Type your voice-over script here...")
        self.txt_script.setMinimumHeight(80)
        self.txt_script.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 10px;
                font-size: 12px;
                line-height: 1.4;
            }
            QTextEdit:focus {
                border: 1px solid #5a9bd6;
            }
        """)
        self.txt_script.setText(text)
        self.txt_script.textChanged.connect(self._on_text_changed)
        txt_layout.addWidget(self.txt_script)
        
        layout.addWidget(self.txt_container)
        
        # Animation for expand/collapse
        from PyQt5.QtCore import QPropertyAnimation
        self._animation = QPropertyAnimation(self.txt_container, b"maximumHeight")
        self._animation.setDuration(200)
        
    def _on_header_click(self):
        """Emit clicked signal for selection."""
        self.clicked.emit(self.idx)
        
    def toggle_expand(self):
        """Animate expand/collapse of script text box."""
        self.expanded = not self.expanded
        
        self._animation.stop()
        if self.expanded:
            self._animation.setStartValue(0)
            self._animation.setEndValue(120)
            self.btn_expand.setText("▲")
        else:
            self._animation.setStartValue(self.txt_container.height())
            self._animation.setEndValue(0)
            self.btn_expand.setText("▼")
        
        self._animation.start()
        
    def _on_text_changed(self):
        """Update preview and emit signal."""
        text = self.txt_script.toPlainText()
        preview = text[:50] + "..." if len(text) > 50 else text if text else "No script yet"
        self.lbl_preview.setText(preview)
        self.text_changed.emit(self.idx, text)

    def update_index(self, new_idx):
        """Update index label."""
        self.idx = new_idx
        self.lbl_title.setText(f"Snippet {new_idx + 1}")
    
    def set_assigned_style(self, assigned):
        """Update style based on assignment status."""
        if assigned:
            self.color_bar.setStyleSheet(f"background-color: #2ecc71; border-radius: 2px;")
            self.lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #2ecc71;")
        else:
            self.color_bar.setStyleSheet(f"background-color: {self.color_hex}; border-radius: 2px;")
            self.lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #fff;")



class SubImageWidget(QWidget):
    """Widget for sub-image overlay in storyboard."""
    deleted = pyqtSignal(str)
    settings_changed = pyqtSignal(str, dict)
    
    def __init__(self, sub_image_id, image_path, total_snips, after_snip):
        super().__init__()
        self.sub_image_id = sub_image_id
        
        self.setStyleSheet("""
            SubImageWidget {
                background-color: #2a3a2a;
                border-radius: 8px;
                border: 1px solid #4caf50;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        
        # Header
        header = QHBoxLayout()
        
        thumb = QLabel()
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(pixmap)
        thumb.setFixedSize(36, 36)
        header.addWidget(thumb)
        
        self.lbl_title = QLabel(f"�� {sub_image_id}")
        self.lbl_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #4caf50;")
        header.addWidget(self.lbl_title, 1)
        
        btn_del = QPushButton("×")
        btn_del.setFixedSize(26, 26)
        btn_del.setStyleSheet("QPushButton { background: transparent; color: #888; border: 1px solid #444; border-radius: 4px; } QPushButton:hover { background: #d32f2f; color: white; }")
        btn_del.clicked.connect(lambda: self.deleted.emit(self.sub_image_id))
        header.addWidget(btn_del)
        
        layout.addLayout(header)
        
        # After snip combo
        from PyQt5.QtWidgets import QComboBox, QCheckBox
        row = QHBoxLayout()
        row.addWidget(QLabel("After:"))
        self.combo = QComboBox()
        self.combo.setStyleSheet("QComboBox { background: #333; color: white; border: 1px solid #555; padding: 3px; border-radius: 3px; }")
        for i in range(max(1, total_snips)):
            self.combo.addItem(f"Snip {i+1}", i)
        self.combo.setCurrentIndex(min(after_snip, self.combo.count()-1))
        self.combo.currentIndexChanged.connect(self._emit)
        row.addWidget(self.combo, 1)
        layout.addLayout(row)
        
        # Persistent checkbox
        self.chk = QCheckBox("Keep until video ends")
        self.chk.setStyleSheet("color: #aaa; font-size: 11px;")
        self.chk.stateChanged.connect(self._emit)
        layout.addWidget(self.chk)
        
        # Script
        self.txt = QTextEdit()
        self.txt.setPlaceholderText("Voice script...")
        self.txt.setMaximumHeight(50)
        self.txt.setStyleSheet("QTextEdit { background: #1e1e1e; color: #ddd; border: 1px solid #444; border-radius: 4px; padding: 5px; font-size: 11px; }")
        self.txt.textChanged.connect(self._emit)
        layout.addWidget(self.txt)
    
    def _emit(self):
        self.settings_changed.emit(self.sub_image_id, {
            'after_snip': self.combo.currentData(),
            'persistent': self.chk.isChecked(),
            'text': self.txt.toPlainText()
        })
