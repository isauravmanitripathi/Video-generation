"""
Sub-Image Handler Module

Handles sub-image overlay processing, rendering, and video segment generation.
Sub-images are rendered as separate video segments and composited in timeline order.
"""

import os
from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable
from PIL import Image
import numpy as np


@dataclass
class SubImageData:
    """Data structure for a sub-image overlay."""
    id: str
    image_path: str
    position: Tuple[int, int]  # (x, y) in source image coordinates
    size: Tuple[int, int]  # (width, height) in source image pixels
    after_snip: int  # Index of snippet to appear after (0-based)
    text: str = ""
    audio_path: Optional[str] = None
    audio_duration: float = 0.0
    persistent: bool = False  # If True, stays until video ends


class SubImageProcessor:
    """
    Processes sub-images for video generation.
    
    Responsibilities:
    - Load and resize sub-images
    - Composite onto source image
    - Calculate timeline positions
    - Generate camera targets for Ken Burns effect
    """
    
    def __init__(self, source_image: Image.Image, sub_images: List[dict]):
        """
        Initialize the processor.
        
        Args:
            source_image: The base PIL Image to composite onto
            sub_images: List of sub-image dicts from GUI
        """
        self.source_image = source_image.copy()
        self.image_width, self.image_height = source_image.size
        
        # Parse and store sub-image data
        self.sub_images: List[SubImageData] = []
        for si in sub_images:
            self.sub_images.append(self._parse_sub_image(si))
        
        # Sort by after_snip to process in order
        self.sub_images.sort(key=lambda x: x.after_snip)
    
    def _parse_sub_image(self, data: dict) -> SubImageData:
        """Parse a sub-image dict into SubImageData."""
        pos = data.get('position', (0, 0))
        size = data.get('size', (100, 100))
        
        return SubImageData(
            id=data.get('id', 'unknown'),
            image_path=data.get('image_path', ''),
            position=(int(pos[0]), int(pos[1])),
            size=(int(size[0]), int(size[1])) if size else (100, 100),
            after_snip=data.get('after_snip', 0),
            text=data.get('text', ''),
            audio_path=data.get('audio_path'),
            audio_duration=data.get('audio_duration', 0.0),
            persistent=data.get('persistent', False)
        )
    
    def composite_all(self) -> Image.Image:
        """
        Composite all sub-images onto the source image.
        
        Returns the composited image with all sub-images baked in.
        """
        result = self.source_image.copy()
        
        for sub_img in self.sub_images:
            result = self._composite_one(result, sub_img)
        
        return result
    
    def _composite_one(self, base: Image.Image, sub_img: SubImageData) -> Image.Image:
        """Composite a single sub-image onto the base image."""
        if not sub_img.image_path or not os.path.exists(sub_img.image_path):
            print(f"Sub-image not found: {sub_img.image_path}")
            return base
        
        try:
            overlay = Image.open(sub_img.image_path).convert('RGBA')
            
            # Resize to specified size
            target_w, target_h = sub_img.size
            if target_w > 0 and target_h > 0:
                overlay = overlay.resize((target_w, target_h), Image.Resampling.LANCZOS)
            
            x, y = sub_img.position
            
            print(f"Compositing {sub_img.id} at ({x}, {y}), size: {overlay.size}")
            
            # Paste with alpha
            if base.mode != 'RGBA':
                base = base.convert('RGBA')
            
            base.paste(overlay, (x, y), overlay)
            
            return base
            
        except Exception as e:
            print(f"Error compositing {sub_img.id}: {e}")
            return base
    
    def get_sub_images_after_snippet(self, snippet_idx: int) -> List[SubImageData]:
        """Get all sub-images that should appear after a specific snippet."""
        return [si for si in self.sub_images if si.after_snip == snippet_idx]
    
    def get_camera_target(self, sub_img: SubImageData) -> dict:
        """
        Get camera target (center point and zoom) for a sub-image.
        
        Returns dict with: center_x, center_y, width, height
        """
        x, y = sub_img.position
        w, h = sub_img.size
        
        return {
            'center_x': x + w // 2,
            'center_y': y + h // 2,
            'width': w,
            'height': h,
            'audio_path': sub_img.audio_path,
            'audio_duration': sub_img.audio_duration
        }
    
    def build_interleaved_timeline(
        self,
        snippets: List[dict],
        intro_duration: float,
        snippet_duration: float,
        hold_duration: float,
        outro_duration: float,
        min_zoom: float = 1.0,
        max_zoom: float = 4.0
    ) -> List[dict]:
        """
        Build a timeline with sub-images interleaved after their respective snippets.
        
        Timeline order:
        - Intro
        - Snippet 0 → Sub-images after snippet 0
        - Snippet 1 → Sub-images after snippet 1
        - ...
        - Outro
        
        Returns list of keyframes.
        """
        keyframes = []
        current_time = 0.0
        
        img_center_x = self.image_width // 2
        img_center_y = self.image_height // 2
        
        # Intro
        keyframes.append({
            'time': current_time,
            'zoom': 1.0,
            'center_x': img_center_x,
            'center_y': img_center_y,
            'type': 'intro',
            'audio_path': None,
            'audio_duration': 0
        })
        
        current_time += intro_duration
        keyframes.append({
            'time': current_time,
            'zoom': 1.0,
            'center_x': img_center_x,
            'center_y': img_center_y,
            'type': 'intro_end',
            'audio_path': None,
            'audio_duration': 0
        })
        
        # Process each snippet
        for i, snippet in enumerate(snippets):
            # Get snippet dimensions
            if hasattr(snippet, 'x'):
                sx, sy, sw, sh = snippet.x, snippet.y, snippet.width, snippet.height
                s_audio_dur = snippet.audio_duration
                s_audio_path = snippet.audio_path
            else:
                sx = snippet.get('x', 0)
                sy = snippet.get('y', 0)
                sw = snippet.get('width', snippet.get('w', 100))
                sh = snippet.get('height', snippet.get('h', 100))
                s_audio_dur = snippet.get('audio_duration', 0)
                s_audio_path = snippet.get('audio_path')
            
            snippet_center_x = sx + sw // 2
            snippet_center_y = sy + sh // 2
            snippet_zoom = self._calculate_zoom(sw, sh, min_zoom, max_zoom, 0.8)
            
            # Animate to snippet
            current_time += snippet_duration
            keyframes.append({
                'time': current_time,
                'zoom': snippet_zoom,
                'center_x': snippet_center_x,
                'center_y': snippet_center_y,
                'type': 'snippet',
                'index': i,
                'audio_path': None,
                'audio_duration': 0
            })
            
            # Hold at snippet
            duration = max(s_audio_dur, hold_duration)
            current_time += duration
            keyframes.append({
                'time': current_time,
                'zoom': snippet_zoom,
                'center_x': snippet_center_x,
                'center_y': snippet_center_y,
                'type': 'snippet_hold',
                'index': i,
                'audio_path': s_audio_path,
                'audio_duration': s_audio_dur
            })
            
            # Add sub-images that appear after this snippet
            sub_images_after = self.get_sub_images_after_snippet(i)
            for si in sub_images_after:
                target = self.get_camera_target(si)
                si_zoom = self._calculate_zoom(target['width'], target['height'], min_zoom, max_zoom, 0.6)
                
                # Animate to sub-image
                current_time += snippet_duration
                keyframes.append({
                    'time': current_time,
                    'zoom': si_zoom,
                    'center_x': target['center_x'],
                    'center_y': target['center_y'],
                    'type': 'sub_image',
                    'id': si.id,
                    'audio_path': None,
                    'audio_duration': 0
                })
                
                # Hold at sub-image
                si_hold = max(si.audio_duration, hold_duration)
                current_time += si_hold
                keyframes.append({
                    'time': current_time,
                    'zoom': si_zoom,
                    'center_x': target['center_x'],
                    'center_y': target['center_y'],
                    'type': 'sub_image_hold',
                    'id': si.id,
                    'audio_path': si.audio_path,
                    'audio_duration': si.audio_duration
                })
        
        # Outro
        current_time += outro_duration
        keyframes.append({
            'time': current_time,
            'zoom': 1.0,
            'center_x': img_center_x,
            'center_y': img_center_y,
            'type': 'outro',
            'audio_path': None,
            'audio_duration': 0
        })
        
        return keyframes
    
    def _calculate_zoom(self, width: int, height: int, min_zoom: float, max_zoom: float, padding: float = 0.8) -> float:
        """Calculate optimal zoom level to fit a region."""
        zoom_x = (self.image_width * padding) / width
        zoom_y = (self.image_height * padding) / height
        zoom = min(zoom_x, zoom_y)
        return max(min_zoom, min(max_zoom, zoom))
