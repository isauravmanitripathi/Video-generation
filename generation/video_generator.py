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
    CompositeAudioClip
)
from generation.sub_image_handler import SubImageProcessor


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


class KenBurnsGenerator:
    """
    Generates Ken Burns style videos from an image with snippet regions.
    
    The video smoothly animates from an overview to each snippet,
    with sub-images appearing after their specified snippets.
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
        
        # Process sub-images with the new handler
        self.sub_image_processor = SubImageProcessor(self.original_image, sub_images or [])
        
        # Composite all sub-images onto source
        self.source_image = self.sub_image_processor.composite_all()
        
        # Build timeline with sub-images interleaved after their respective snippets
        self.timeline = self.sub_image_processor.build_interleaved_timeline(
            snippets=self.snippets,
            intro_duration=self.intro_duration,
            snippet_duration=self.snippet_duration,
            hold_duration=self.hold_duration,
            outro_duration=self.outro_duration,
            min_zoom=self.min_zoom,
            max_zoom=self.max_zoom
        )
        
        # Debug: print timeline
        print("\n=== Timeline ===")
        for kf in self.timeline:
            print(f"  {kf['time']:.2f}s - {kf['type']} @ ({kf['center_x']}, {kf['center_y']}) zoom={kf['zoom']:.2f}")
        print("================\n")
    
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
            
            # Build audio from timeline keyframes
            audio_clips = []
            
            for kf in self.timeline:
                audio_path = kf.get('audio_path')
                if audio_path and os.path.exists(audio_path):
                    # Audio starts at the beginning of the "hold" phase
                    # Find the matching hold keyframe
                    if '_hold' in kf['type']:
                        # Get the start time (previous keyframe's time)
                        idx = self.timeline.index(kf)
                        if idx > 0:
                            audio_start = self.timeline[idx - 1]['time']
                        else:
                            audio_start = kf['time']
                        
                        try:
                            audio = AudioFileClip(audio_path)
                            audio = audio.with_start(audio_start)
                            audio_clips.append(audio)
                            print(f"Audio for {kf['type']} at {audio_start:.2f}s")
                        except Exception as e:
                            print(f"Failed to load audio {audio_path}: {e}")
            
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
