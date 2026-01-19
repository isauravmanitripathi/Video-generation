"""
Frame Renderer Module

Renders individual video frames with different modes:
- ZoomRenderer: Zooms/pans to snippets and sub-images
- StaticRenderer: Shows full image with box overlays
"""

import numpy as np
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from generation.timeline_builder import TimelineEvent


class BaseRenderer:
    """Base class for frame renderers."""
    
    def __init__(
        self,
        source_image: Image.Image,
        output_width: int = 1080,
        output_height: int = 1920,
        show_boxes: bool = True,
        box_color: str = "red",
        box_thickness: int = 4
    ):
        self.source_image = source_image
        self.image_width, self.image_height = source_image.size
        self.output_width = output_width
        self.output_height = output_height
        self.show_boxes = show_boxes
        self.box_color = box_color
        self.box_thickness = box_thickness
    
    def render_frame(self, t: float, events: List[TimelineEvent], visible_sub_images: List[dict]) -> np.ndarray:
        """Render a frame at time t. Override in subclasses."""
        raise NotImplementedError


class ZoomRenderer(BaseRenderer):
    """
    Renders frames with zoom/pan effect.
    Camera moves to center on current snippet/sub-image with appropriate zoom.
    """
    
    def __init__(self, *args, use_ken_burns: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_ken_burns = use_ken_burns
    
    def render_frame(
        self,
        t: float,
        events: List[TimelineEvent],
        visible_sub_images: List[dict] = None
    ) -> np.ndarray:
        """Render a zoomed frame at time t."""
        # Get camera state at this time
        state = self._interpolate_camera(t, events)
        
        zoom = state['zoom']
        center_x = state['center_x']
        center_y = state['center_y']
        
        # Calculate visible region
        visible_width = self.image_width / zoom
        visible_height = self.image_height / zoom
        
        # Calculate crop box
        left = center_x - visible_width / 2
        top = center_y - visible_height / 2
        right = center_x + visible_width / 2
        bottom = center_y + visible_height / 2
        
        # Clamp to bounds
        if left < 0:
            right -= left
            left = 0
        if top < 0:
            bottom -= top
            top = 0
        if right > self.image_width:
            left -= (right - self.image_width)
            right = self.image_width
        if bottom > self.image_height:
            top -= (bottom - self.image_height)
            bottom = self.image_height
        
        left = max(0, left)
        top = max(0, top)
        right = min(self.image_width, right)
        bottom = min(self.image_height, bottom)
        
        # Crop and resize
        cropped = self.source_image.crop((int(left), int(top), int(right), int(bottom)))
        frame = cropped.resize((self.output_width, self.output_height), Image.Resampling.LANCZOS)
        
        # Draw box if enabled and there's a current box_rect
        if self.show_boxes and state.get('box_rect'):
            frame = self._draw_box(frame, state['box_rect'], left, top, visible_width, visible_height)
        
        # Convert to RGB
        frame = self._to_rgb(frame)
        
        return np.array(frame)
    
    def _interpolate_camera(self, t: float, events: List[TimelineEvent]) -> dict:
        """Interpolate camera position at time t."""
        if not events:
            return {
                'zoom': 1.0,
                'center_x': self.image_width // 2,
                'center_y': self.image_height // 2,
                'box_rect': None
            }
        
        # Find current and next event
        current_event = events[0]
        next_event = None
        
        for i, event in enumerate(events):
            if event.time <= t:
                current_event = event
                if i + 1 < len(events):
                    next_event = events[i + 1]
            else:
                break
        
        if not self.use_ken_burns or not next_event or t >= next_event.time:
            # No interpolation
            return {
                'zoom': current_event.zoom,
                'center_x': current_event.center_x,
                'center_y': current_event.center_y,
                'box_rect': current_event.box_rect
            }
        
        # Interpolate between current and next
        event_duration = next_event.time - current_event.time
        if event_duration == 0:
            progress = 1.0
        else:
            progress = (t - current_event.time) / event_duration
        
        # Smoothstep easing
        eased = self._smoothstep(progress)
        
        return {
            'zoom': current_event.zoom + (next_event.zoom - current_event.zoom) * eased,
            'center_x': current_event.center_x + (next_event.center_x - current_event.center_x) * eased,
            'center_y': current_event.center_y + (next_event.center_y - current_event.center_y) * eased,
            'box_rect': current_event.box_rect
        }
    
    def _smoothstep(self, t: float) -> float:
        """Smooth ease-in-out: 3t² - 2t³"""
        t = max(0, min(1, t))
        return t * t * (3 - 2 * t)
    
    def _draw_box(self, frame: Image.Image, box_rect: Tuple, left: float, top: float, vis_w: float, vis_h: float) -> Image.Image:
        """Draw a box overlay on the frame."""
        bx, by, bw, bh = box_rect
        
        # Transform to frame coordinates
        scale_x = self.output_width / vis_w
        scale_y = self.output_height / vis_h
        
        fx = int((bx - left) * scale_x)
        fy = int((by - top) * scale_y)
        fw = int(bw * scale_x)
        fh = int(bh * scale_y)
        
        draw = ImageDraw.Draw(frame)
        draw.rectangle([fx, fy, fx + fw, fy + fh], outline=self.box_color, width=self.box_thickness)
        
        return frame
    
    def _to_rgb(self, img: Image.Image) -> Image.Image:
        """Convert image to RGB."""
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (0, 0, 0))
            background.paste(img, mask=img.split()[3])
            return background
        return img.convert('RGB')


class StaticRenderer(BaseRenderer):
    """
    Renders frames showing the full image.
    Uses box overlays to highlight current snippet.
    Sub-images appear/disappear based on visibility.
    """
    
    def __init__(self, *args, sub_images: List[dict] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sub_images = sub_images or []
        
        # Pre-load sub-image PIL objects
        self._load_sub_images()
        
        # Cache the base frame (full image without sub-images)
        self.base_frame = self._prepare_base_frame()
    
    def _load_sub_images(self):
        """Load sub-image PIL objects."""
        import os
        for si in self.sub_images:
            img_path = si.get('image_path', '')
            size = si.get('size', (100, 100))
            
            if img_path and os.path.exists(img_path):
                try:
                    img = Image.open(img_path).convert('RGBA')
                    # Resize to specified size
                    if size:
                        img = img.resize((int(size[0]), int(size[1])), Image.Resampling.LANCZOS)
                    si['_pil_image'] = img
                except Exception as e:
                    print(f"Failed to load sub-image: {e}")
                    si['_pil_image'] = None
            else:
                si['_pil_image'] = None
    
    def _prepare_base_frame(self) -> Image.Image:
        """Prepare the base frame (full image scaled to output size)."""
        # Scale source image to fit output while maintaining aspect ratio
        src_aspect = self.image_width / self.image_height
        out_aspect = self.output_width / self.output_height
        
        if src_aspect > out_aspect:
            # Source is wider - fit by width
            new_width = self.output_width
            new_height = int(self.output_width / src_aspect)
        else:
            # Source is taller - fit by height
            new_height = self.output_height
            new_width = int(self.output_height * src_aspect)
        
        # Create output frame with black background
        frame = Image.new('RGB', (self.output_width, self.output_height), (0, 0, 0))
        
        # Resize and center the source image
        resized = self.source_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        x_offset = (self.output_width - new_width) // 2
        y_offset = (self.output_height - new_height) // 2
        
        # Convert to RGB if needed
        if resized.mode == 'RGBA':
            frame.paste(resized, (x_offset, y_offset), resized.split()[3])
        else:
            frame.paste(resized, (x_offset, y_offset))
        
        # Store offsets for coordinate transformations
        self._x_offset = x_offset
        self._y_offset = y_offset
        self._scale = new_width / self.image_width
        
        return frame
    
    def render_frame(
        self,
        t: float,
        events: List[TimelineEvent],
        visible_sub_images: List[dict] = None
    ) -> np.ndarray:
        """Render a static frame at time t with overlays."""
        # Start with base frame copy
        frame = self.base_frame.copy()
        
        # Find current event for box overlay
        current_event = self._get_current_event(t, events)
        
        # Draw box overlay for current snippet
        if self.show_boxes and current_event and current_event.box_rect:
            frame = self._draw_box_overlay(frame, current_event.box_rect)
        
        # Overlay visible sub-images
        if visible_sub_images:
            for si in visible_sub_images:
                frame = self._overlay_sub_image(frame, si)
        
        return np.array(frame)
    
    def _get_current_event(self, t: float, events: List[TimelineEvent]) -> Optional[TimelineEvent]:
        """Get the event active at time t."""
        for event in reversed(events):
            if event.time <= t:
                return event
        return events[0] if events else None
    
    def _draw_box_overlay(self, frame: Image.Image, box_rect: Tuple) -> Image.Image:
        """Draw a highlighted box around a region."""
        bx, by, bw, bh = box_rect
        
        # Transform source coordinates to frame coordinates
        fx = int(bx * self._scale + self._x_offset)
        fy = int(by * self._scale + self._y_offset)
        fw = int(bw * self._scale)
        fh = int(bh * self._scale)
        
        draw = ImageDraw.Draw(frame)
        
        # Draw outer glow effect
        for i in range(3):
            offset = i * 2
            alpha = 100 - i * 30
            draw.rectangle(
                [fx - offset, fy - offset, fx + fw + offset, fy + fh + offset],
                outline=self.box_color,
                width=self.box_thickness - i
            )
        
        # Draw main box
        draw.rectangle(
            [fx, fy, fx + fw, fy + fh],
            outline=self.box_color,
            width=self.box_thickness
        )
        
        return frame
    
    def _overlay_sub_image(self, frame: Image.Image, sub_img: dict) -> Image.Image:
        """Overlay a sub-image onto the frame."""
        pil_img = sub_img.get('_pil_image')
        if not pil_img:
            return frame
        
        pos = sub_img.get('position', (0, 0))
        
        # Transform source coordinates to frame coordinates
        fx = int(pos[0] * self._scale + self._x_offset)
        fy = int(pos[1] * self._scale + self._y_offset)
        
        # Scale sub-image
        new_w = int(pil_img.width * self._scale)
        new_h = int(pil_img.height * self._scale)
        
        if new_w > 0 and new_h > 0:
            scaled = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # Paste with alpha
            if frame.mode != 'RGBA':
                frame = frame.convert('RGBA')
            
            frame.paste(scaled, (fx, fy), scaled)
            
            # Convert back to RGB
            frame = frame.convert('RGB')
        
        return frame
