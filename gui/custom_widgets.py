from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTextEdit, 
                             QFileDialog, QFrame, QSizePolicy, QGesture,
                             QPinchGesture)
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
    file_dropped_signal = pyqtSignal(str) # New Signal
    
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
            
            painter.restore()
        
        # 5. Draw Viewport Border
        pen = QPen(QColor("#5a9bd6"), 2)
        painter.setPen(pen)
        painter.drawRect(self.viewport_rect)
        
    def mousePressEvent(self, event):
        if self.source_pixmap and self.viewport_rect.contains(event.pos()):
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            
    def mouseMoveEvent(self, event):
        if self.is_dragging and self.source_pixmap:
            delta = event.pos() - self.last_mouse_pos
            self.image_pos += delta
            self.last_mouse_pos = event.pos()
            
            # Log Coordinates relative to the source image?
            # User wants to know "what coordinate from that image is shown"
            # The viewport top-left in Image Space.
            
            # Coordinate Math:
            # Viewport Center (Screen) corresponds to Image Center + offset (Screen Px)
            # We need to map Viewport Top-Left back to Image Coordinates.
            
            # Image Top-Left (Screen) = Viewport Center - (ImgWidth/2) + Offset
            # Viewport Top-Left (Screen relative to Image Top-Left) = - (Image Top-Left relative to Viewport)
            
            # Simplified: 
            # Scale Factor = self.scale_factor
            # Offset X (Screen) = self.image_pos.x()
            
            # Image Center X (Screen) = Viewport Center + Offset X
            # Viewport Center = Image Center X - Offset X
            
            src_w = self.source_pixmap.width()
            src_h = self.source_pixmap.height()
            
            dw = src_w * self.scale_factor
            dh = src_h * self.scale_factor
            
            # Viewport Top-Left in "Screen relative to Image Top-Left"
            # img_tl_x = (vp_w/2) - (dw/2) + offset_x
            # vp_tl_x relative to img_tl: -img_tl_x
            # = - ( (vp_w/2) - (dw/2) + offset_x )
            # = (dw/2) - (vp_w/2) - offset_x
            
            vp_w = self.viewport_rect.width()
            vp_h = self.viewport_rect.height()
            
            screen_crop_x = (dw - vp_w)/2 - self.image_pos.x()
            screen_crop_y = (dh - vp_h)/2 - self.image_pos.y()
            
            # Convert to Source Coordinates
            source_crop_x = int(screen_crop_x / self.scale_factor)
            source_crop_y = int(screen_crop_y / self.scale_factor)
            source_crop_w = int(vp_w / self.scale_factor)
            source_crop_h = int(vp_h / self.scale_factor)
            
            self.log_signal.emit(f"Crop Rect: x={source_crop_x}, y={source_crop_y}, w={source_crop_w}, h={source_crop_h}")
            
            self.update()
            
    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.setCursor(Qt.ArrowCursor)
