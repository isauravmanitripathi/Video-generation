"""
Ken Burns Video Generator - MoviePy Implementation

Generates videos with smooth zoom/pan animations through image snippets.
Uses MoviePy for frame-by-frame animation with proper sub-image overlay support.
"""

import os
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable
from PIL import Image
from moviepy import (
    VideoClip, CompositeVideoClip, AudioFileClip, 
    CompositeAudioClip, concatenate_audioclips
)


@dataclass
class Snippet:
    """Represents a region of interest in the source image."""
    x: int
    y: int
    width: int
    height: int
    text: str = ""
    audio_path: Optional[str] = None
    audio_duration: float = 0.0


@dataclass 
class SubImageTarget:
    """Represents a sub-image overlay that acts as a camera target."""
    x: int  # Position on source image
    y: int
    width: int
    height: int
    pil_image: Image.Image  # The overlay image
    audio_path: Optional[str] = None
    audio_duration: float = 0.0


class KenBurnsGenerator:
    """
    Generates Ken Burns style videos from an image with snippet regions.
    
    The video smoothly animates from an overview to each snippet,
    zooming in/out intelligently based on snippet size.
    Sub-images are composited onto the source and treated as camera targets.
    """
    
    def __init__(
        self,
        image_path: str,
        snippets: List[dict],
        output_width: int = 1080,
        output_height: int = 1920,
        fps: int = 30,
        intro_duration: float = 2.0,
        snippet_duration: float = 3.0,
        hold_duration: float = 1.0,
        outro_duration: float = 2.0,
        min_zoom: float = 1.0,
        max_zoom: float = 4.0,
        show_boxes: bool = False,
        box_color: str = "red",
        box_thickness: int = 4,
        ken_burns: bool = True,
        sub_images: List[dict] = None
    ):
        self.image_path = image_path
        self.output_width = output_width
        self.output_height = output_height
        self.fps = fps
        self.ken_burns = ken_burns
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom
        self.show_boxes = show_boxes
        self.box_color = box_color
        self.box_thickness = box_thickness
        
        # Normalize snippets to Snippet objects
        self.snippets = []
        for s in snippets:
            if isinstance(s, dict):
                valid_keys = {k: v for k, v in s.items() if k in Snippet.__annotations__}
                self.snippets.append(Snippet(**valid_keys))
            else:
                self.snippets.append(s)
        
        # When Ken Burns is disabled, set animation durations to 0 (instant cuts)
        if ken_burns:
            self.intro_duration = intro_duration
            self.snippet_duration = snippet_duration
            self.outro_duration = outro_duration
        else:
            self.intro_duration = 0.0
            self.snippet_duration = 0.0
            self.outro_duration = 0.0
        
        self.hold_duration = hold_duration
        
        # Load source image
        self.original_image = Image.open(image_path).convert('RGBA')
        self.image_width, self.image_height = self.original_image.size
        
        # Process sub-images: composite onto source AND create targets
        self.sub_image_targets = []
        self.source_image = self._composite_sub_images(sub_images or [])
        
        # Calculate timeline (includes sub-image targets)
        self.timeline = self._build_timeline()
    
    def _composite_sub_images(self, sub_images: List[dict]) -> Image.Image:
        """
        Composite sub-images onto the source image.
        Also creates SubImageTarget objects for camera movement.
        
        Returns the composited image.
        """
        result = self.original_image.copy()
        
        for sub_img in sub_images:
            img_path = sub_img.get('image_path', '')
            if not img_path or not os.path.exists(img_path):
                print(f"Sub-image not found: {img_path}")
                continue
            
            try:
                overlay = Image.open(img_path).convert('RGBA')
                
                # Get position in source coordinates
                pos = sub_img.get('position', (0, 0))
                x, y = int(pos[0]), int(pos[1])
                
                print(f"Compositing sub-image at ({x}, {y}), size: {overlay.size}")
                
                # Paste overlay onto result
                result.paste(overlay, (x, y), overlay)
                
                # Create a target for camera movement
                # The target area is the bounding box of the sub-image
                target = SubImageTarget(
                    x=x,
                    y=y,
                    width=overlay.width,
                    height=overlay.height,
                    pil_image=overlay,
                    audio_path=sub_img.get('audio_path'),
                    audio_duration=sub_img.get('audio_duration', 0.0)
                )
                self.sub_image_targets.append(target)
                
            except Exception as e:
                print(f"Failed to composite sub-image {img_path}: {e}")
        
        return result
    
    def _calculate_zoom_for_region(self, width: int, height: int) -> float:
        """
        Calculate optimal zoom level to fit a region in viewport.
        """
        padding_factor = 0.6  # Show the sub-image with more context
        
        zoom_x = (self.image_width * padding_factor) / width
        zoom_y = (self.image_height * padding_factor) / height
        
        zoom = min(zoom_x, zoom_y)
        return max(self.min_zoom, min(self.max_zoom, zoom))
    
    def _calculate_zoom_for_snippet(self, snippet: Snippet) -> float:
        """Calculate optimal zoom level to fit snippet in viewport."""
        padding_factor = 0.8
        
        zoom_x = (self.image_width * padding_factor) / snippet.width
        zoom_y = (self.image_height * padding_factor) / snippet.height
        
        zoom = min(zoom_x, zoom_y)
        return max(self.min_zoom, min(self.max_zoom, zoom))
    
    def _build_timeline(self) -> List[dict]:
        """
        Build a timeline of keyframes for the animation.
        
        Timeline order:
        1. Intro (overview)
        2. Each snippet (with hold for audio)
        3. Each sub-image target (camera pans to sub-image location)
        4. Outro (back to overview)
        """
        keyframes = []
        current_time = 0.0
        
        # Image center for overview shots
        img_center_x = self.image_width // 2
        img_center_y = self.image_height // 2
        
        # Intro: show overview
        keyframes.append({
            'time': current_time,
            'zoom': 1.0,
            'center_x': img_center_x,
            'center_y': img_center_y,
            'type': 'intro'
        })
        
        current_time += self.intro_duration
        keyframes.append({
            'time': current_time,
            'zoom': 1.0,
            'center_x': img_center_x,
            'center_y': img_center_y,
            'type': 'intro_end'
        })
        
        # For each snippet
        for i, snippet in enumerate(self.snippets):
            snippet_center_x = snippet.x + snippet.width // 2
            snippet_center_y = snippet.y + snippet.height // 2
            snippet_zoom = self._calculate_zoom_for_snippet(snippet)
            
            # Animate to snippet
            current_time += self.snippet_duration
            keyframes.append({
                'time': current_time,
                'zoom': snippet_zoom,
                'center_x': snippet_center_x,
                'center_y': snippet_center_y,
                'type': 'snippet',
                'index': i
            })
            
            # Hold at snippet
            duration = max(snippet.audio_duration, self.hold_duration)
            current_time += duration
            keyframes.append({
                'time': current_time,
                'zoom': snippet_zoom,
                'center_x': snippet_center_x,
                'center_y': snippet_center_y,
                'type': 'snippet_hold',
                'index': i
            })
        
        # For each sub-image target - camera pans to the sub-image location
        for i, target in enumerate(self.sub_image_targets):
            target_center_x = target.x + target.width // 2
            target_center_y = target.y + target.height // 2
            target_zoom = self._calculate_zoom_for_region(target.width, target.height)
            
            # Animate to sub-image location
            current_time += self.snippet_duration
            keyframes.append({
                'time': current_time,
                'zoom': target_zoom,
                'center_x': target_center_x,
                'center_y': target_center_y,
                'type': 'sub_image',
                'index': i
            })
            
            # Hold at sub-image
            duration = max(target.audio_duration, self.hold_duration)
            current_time += duration
            keyframes.append({
                'time': current_time,
                'zoom': target_zoom,
                'center_x': target_center_x,
                'center_y': target_center_y,
                'type': 'sub_image_hold',
                'index': i
            })
        
        # Outro: return to overview
        current_time += self.outro_duration
        keyframes.append({
            'time': current_time,
            'zoom': 1.0,
            'center_x': img_center_x,
            'center_y': img_center_y,
            'type': 'outro'
        })
        
        return keyframes
    
    def _smoothstep(self, t: float) -> float:
        """Smooth ease-in-out function: 3t² - 2t³"""
        t = max(0, min(1, t))
        return t * t * (3 - 2 * t)
    
    def _interpolate_at_time(self, t: float) -> dict:
        """Get interpolated camera state at time t."""
        if not self.timeline or len(self.timeline) < 2:
            return {'zoom': 1.0, 'center_x': self.image_width // 2, 'center_y': self.image_height // 2}
        
        # Find the two keyframes we're between
        for i in range(len(self.timeline) - 1):
            kf1 = self.timeline[i]
            kf2 = self.timeline[i + 1]
            
            if kf1['time'] <= t <= kf2['time']:
                # Calculate progress
                duration = kf2['time'] - kf1['time']
                if duration == 0:
                    progress = 1.0
                else:
                    progress = (t - kf1['time']) / duration
                
                # Apply smoothstep easing
                eased = self._smoothstep(progress)
                
                # Interpolate values
                return {
                    'zoom': kf1['zoom'] + (kf2['zoom'] - kf1['zoom']) * eased,
                    'center_x': kf1['center_x'] + (kf2['center_x'] - kf1['center_x']) * eased,
                    'center_y': kf1['center_y'] + (kf2['center_y'] - kf1['center_y']) * eased
                }
        
        # Beyond timeline - return last state
        last = self.timeline[-1]
        return {'zoom': last['zoom'], 'center_x': last['center_x'], 'center_y': last['center_y']}
    
    def _render_frame(self, t: float) -> np.ndarray:
        """
        Render a single frame at time t.
        
        This applies the Ken Burns zoom/pan to the composited image
        (which already has sub-images baked in).
        """
        # Get camera state at this time
        state = self._interpolate_at_time(t)
        zoom = state['zoom']
        center_x = state['center_x']
        center_y = state['center_y']
        
        # Calculate visible region in source coords
        visible_width = self.image_width / zoom
        visible_height = self.image_height / zoom
        
        # Calculate crop box (centered on center_x, center_y)
        left = center_x - visible_width / 2
        top = center_y - visible_height / 2
        right = center_x + visible_width / 2
        bottom = center_y + visible_height / 2
        
        # Clamp to image bounds
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
        
        # Crop and resize from the composited image (includes sub-images)
        cropped = self.source_image.crop((int(left), int(top), int(right), int(bottom)))
        resized = cropped.resize((self.output_width, self.output_height), Image.Resampling.LANCZOS)
        
        # Draw boxes if enabled
        if self.show_boxes:
            from PIL import ImageDraw
            draw = ImageDraw.Draw(resized)
            
            for i, snippet in enumerate(self.snippets):
                # Transform snippet coords to frame coords
                box_left = int((snippet.x - left) * (self.output_width / visible_width))
                box_top = int((snippet.y - top) * (self.output_height / visible_height))
                box_right = int((snippet.x + snippet.width - left) * (self.output_width / visible_width))
                box_bottom = int((snippet.y + snippet.height - top) * (self.output_height / visible_height))
                
                # Draw box
                draw.rectangle(
                    [box_left, box_top, box_right, box_bottom],
                    outline=self.box_color,
                    width=self.box_thickness
                )
        
        # Convert to RGB for video output
        if resized.mode == 'RGBA':
            background = Image.new('RGB', resized.size, (0, 0, 0))
            background.paste(resized, mask=resized.split()[3])
            resized = background
        
        return np.array(resized)
    
    def get_total_duration(self) -> float:
        """Get total video duration in seconds."""
        if not self.timeline:
            return 0
        return self.timeline[-1]['time']
    
    def generate(self, output_path: str, progress_callback: Callable[[str], None] = None) -> Tuple[bool, str]:
        """
        Generate the video.
        
        Args:
            output_path: Path for output video file
            progress_callback: Optional callback for progress updates
        
        Returns:
            Tuple of (success, message)
        """
        if not self.snippets:
            return False, "No snippets defined. Create at least one snippet first."
        
        if progress_callback:
            progress_callback("Starting video generation...")
        
        try:
            total_duration = self.get_total_duration()
            
            if progress_callback:
                progress_callback(f"Rendering {total_duration:.1f}s video at {self.fps}fps...")
            
            # Create video clip using make_frame function
            def make_frame(t):
                return self._render_frame(t)
            
            video = VideoClip(make_frame, duration=total_duration).with_fps(self.fps)
            
            # Build audio
            audio_clips = []
            current_time = self.intro_duration
            
            # Snippet audio
            for i, snippet in enumerate(self.snippets):
                # Move to snippet
                current_time += self.snippet_duration
                
                # Audio plays during hold
                if snippet.audio_path and os.path.exists(snippet.audio_path):
                    try:
                        audio = AudioFileClip(snippet.audio_path)
                        audio = audio.with_start(current_time)
                        audio_clips.append(audio)
                        print(f"Snippet {i+1} audio at {current_time:.2f}s")
                    except Exception as e:
                        print(f"Failed to load audio {snippet.audio_path}: {e}")
                
                # Hold duration
                hold_dur = max(snippet.audio_duration, self.hold_duration)
                current_time += hold_dur
            
            # Sub-image target audio (after all snippets)
            for i, target in enumerate(self.sub_image_targets):
                # Move to sub-image
                current_time += self.snippet_duration
                
                if target.audio_path and os.path.exists(target.audio_path):
                    try:
                        audio = AudioFileClip(target.audio_path)
                        audio = audio.with_start(current_time)
                        audio_clips.append(audio)
                        print(f"Sub-image {i+1} audio at {current_time:.2f}s")
                    except Exception as e:
                        print(f"Failed to load sub-image audio {target.audio_path}: {e}")
                
                # Hold duration
                hold_dur = max(target.audio_duration, self.hold_duration)
                current_time += hold_dur
            
            # Combine audio
            if audio_clips:
                if progress_callback:
                    progress_callback("Combining audio...")
                final_audio = CompositeAudioClip(audio_clips)
                video = video.with_audio(final_audio)
            
            # Write video
            if progress_callback:
                progress_callback("Encoding video...")
            
            video.write_videofile(
                output_path,
                fps=self.fps,
                codec='libx264',
                audio_codec='aac',
                preset='medium',
                threads=4,
                logger=None  # Suppress moviepy logs
            )
            
            # Cleanup
            video.close()
            for clip in audio_clips:
                clip.close()
            
            return True, f"Video generated successfully: {output_path}"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Error: {str(e)}"


def generate_video_from_snippets(
    image_path: str,
    snippets: List[dict],
    output_path: str,
    aspect_ratio: str = "9:16",
    show_boxes: bool = False,
    ken_burns: bool = True,
    progress_callback: Callable[[str], None] = None,
    sub_images: List[dict] = None
) -> Tuple[bool, str]:
    """
    Convenience function to generate a Ken Burns video.
    
    Args:
        image_path: Path to source image
        snippets: List of snippet dicts with x, y, w, h keys
        output_path: Path for output video
        aspect_ratio: "9:16", "16:9", or "1:1"
        show_boxes: Whether to show box overlay around snippets
        ken_burns: Whether to use Ken Burns animation (True) or instant cuts (False)
        progress_callback: Optional callback for progress
        sub_images: List of sub-image overlay dicts
    
    Returns:
        Tuple of (success, message)
    """
    # Determine output dimensions based on aspect ratio
    if "9:16" in aspect_ratio:
        width, height = 1080, 1920
    elif "16:9" in aspect_ratio:
        width, height = 1920, 1080
    else:
        width, height = 1080, 1080
    
    # Convert snippet format
    normalized_snippets = []
    for s in snippets:
        if 'source_rect' in s:
            # From canvas format
            rect = s['source_rect']
            normalized_snippets.append({
                'x': rect.x(),
                'y': rect.y(),
                'width': rect.width(),
                'height': rect.height(),
                'audio_path': s.get('audio_path'),
                'audio_duration': s.get('audio_duration', 0.0)
            })
        elif 'w' in s:
            # Already in dict format with w/h
            normalized_snippets.append({
                'x': s['x'],
                'y': s['y'],
                'width': s['w'],
                'height': s['h'],
                'audio_path': s.get('audio_path'),
                'audio_duration': s.get('audio_duration', 0.0)
            })
        else:
            normalized_snippets.append(s)
    
    generator = KenBurnsGenerator(
        image_path=image_path,
        snippets=normalized_snippets,
        output_width=width,
        output_height=height,
        show_boxes=show_boxes,
        ken_burns=ken_burns,
        sub_images=sub_images or []
    )
    
    return generator.generate(output_path, progress_callback)
