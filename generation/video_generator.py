"""
Ken Burns Video Generator

Generates videos with smooth zoom/pan animations through image snippets.
Uses ffmpeg zoompan filter for frame-by-frame animation.
"""

import subprocess
import os
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class Keyframe:
    """Represents a camera position at a specific frame."""
    frame: int
    zoom: float  # 1.0 = original size, 2.0 = 2x zoom
    center_x: int  # Center point in source image coords
    center_y: int  # Center point in source image coords


@dataclass
class Snippet:
    """Represents a region of interest in the source image."""
    x: int
    y: int
    width: int
    height: int


class KenBurnsGenerator:
    """
    Generates Ken Burns style videos from an image with snippet regions.
    
    The video smoothly animates from an overview to each snippet,
    zooming in/out intelligently based on snippet size.
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
        max_zoom: float = 4.0
    ):
        self.image_path = image_path
        self.snippets = [Snippet(**s) if isinstance(s, dict) else s for s in snippets]
        self.output_width = output_width
        self.output_height = output_height
        self.fps = fps
        self.intro_duration = intro_duration
        self.snippet_duration = snippet_duration
        self.hold_duration = hold_duration
        self.outro_duration = outro_duration
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom
        
        # Get image dimensions
        self.image_width, self.image_height = self._get_image_dimensions()
        
        # Calculate keyframes
        self.keyframes = self._calculate_keyframes()
    
    def _get_image_dimensions(self) -> Tuple[int, int]:
        """Get source image dimensions using ffprobe."""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'csv=s=x:p=0',
                self.image_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            width, height = map(int, result.stdout.strip().split('x'))
            return width, height
        except Exception as e:
            # Fallback - assume 1920x1080 if ffprobe fails
            print(f"Warning: Could not get image dimensions: {e}")
            return 1920, 1080
    
    def _calculate_zoom_for_snippet(self, snippet: Snippet) -> float:
        """
        Calculate optimal zoom level to fit snippet in viewport.
        
        Smaller snippets → higher zoom (to see detail)
        Larger snippets → lower zoom (to fit content)
        """
        # Calculate what zoom would fit the snippet nicely with some padding
        padding_factor = 0.8  # Leave 20% padding around snippet
        
        # How much of the output frame should the snippet fill?
        zoom_x = (self.output_width * padding_factor) / snippet.width
        zoom_y = (self.output_height * padding_factor) / snippet.height
        
        # Use the smaller zoom to ensure snippet fits
        zoom = min(zoom_x, zoom_y)
        
        # Clamp to reasonable range
        return max(self.min_zoom, min(self.max_zoom, zoom))
    
    def _calculate_keyframes(self) -> List[Keyframe]:
        """
        Calculate all keyframes for the animation.
        
        Timeline:
        - Intro: Full image overview
        - Per snippet: Animate to snippet, hold
        - Outro: Return to overview
        """
        keyframes = []
        current_frame = 0
        
        # Image center for overview shots
        img_center_x = self.image_width // 2
        img_center_y = self.image_height // 2
        
        # Intro keyframe (start)
        keyframes.append(Keyframe(
            frame=current_frame,
            zoom=1.0,
            center_x=img_center_x,
            center_y=img_center_y
        ))
        
        # End of intro
        current_frame += int(self.intro_duration * self.fps)
        keyframes.append(Keyframe(
            frame=current_frame,
            zoom=1.0,
            center_x=img_center_x,
            center_y=img_center_y
        ))
        
        # Keyframes for each snippet
        for snippet in self.snippets:
            snippet_center_x = snippet.x + snippet.width // 2
            snippet_center_y = snippet.y + snippet.height // 2
            snippet_zoom = self._calculate_zoom_for_snippet(snippet)
            
            # Animate to snippet
            current_frame += int(self.snippet_duration * self.fps)
            keyframes.append(Keyframe(
                frame=current_frame,
                zoom=snippet_zoom,
                center_x=snippet_center_x,
                center_y=snippet_center_y
            ))
            
            # Hold at snippet
            current_frame += int(self.hold_duration * self.fps)
            keyframes.append(Keyframe(
                frame=current_frame,
                zoom=snippet_zoom,
                center_x=snippet_center_x,
                center_y=snippet_center_y
            ))
        
        # Outro - return to overview
        current_frame += int(self.outro_duration * self.fps)
        keyframes.append(Keyframe(
            frame=current_frame,
            zoom=1.0,
            center_x=img_center_x,
            center_y=img_center_y
        ))
        
        return keyframes
    
    def _build_zoom_expression(self) -> str:
        """Build ffmpeg expression for zoom based on keyframes."""
        if len(self.keyframes) < 2:
            return "1"
        
        parts = []
        for i in range(len(self.keyframes) - 1):
            kf1 = self.keyframes[i]
            kf2 = self.keyframes[i + 1]
            
            frame_diff = kf2.frame - kf1.frame
            if frame_diff == 0:
                continue
            
            # Linear interpolation between keyframes
            # lerp formula: start + (end - start) * progress
            progress = f"(on-{kf1.frame})/{frame_diff}"
            lerp = f"{kf1.zoom}+({kf2.zoom}-{kf1.zoom})*{progress}"
            
            if i == 0:
                condition = f"lt(on,{kf2.frame})"
            else:
                condition = f"between(on,{kf1.frame},{kf2.frame})"
            
            parts.append(f"if({condition},{lerp}")
        
        # Close all if statements and add final value
        expr = ""
        for part in parts:
            expr += part + ","
        expr += str(self.keyframes[-1].zoom)
        expr += ")" * len(parts)
        
        return expr
    
    def _build_x_expression(self) -> str:
        """Build ffmpeg expression for x pan based on keyframes."""
        if len(self.keyframes) < 2:
            return f"(iw-iw/zoom)/2"
        
        parts = []
        for i in range(len(self.keyframes) - 1):
            kf1 = self.keyframes[i]
            kf2 = self.keyframes[i + 1]
            
            frame_diff = kf2.frame - kf1.frame
            if frame_diff == 0:
                continue
            
            progress = f"(on-{kf1.frame})/{frame_diff}"
            
            # Calculate x position: center_x - (viewport_width/2)
            # In zoompan, x is top-left corner of visible area
            # visible_width = iw/zoom, so x = center_x - (iw/zoom)/2
            x1 = f"({kf1.center_x}-(iw/zoom)/2)"
            x2 = f"({kf2.center_x}-(iw/zoom)/2)"
            lerp = f"{kf1.center_x}+({kf2.center_x}-{kf1.center_x})*{progress}-(iw/zoom)/2"
            
            if i == 0:
                condition = f"lt(on,{kf2.frame})"
            else:
                condition = f"between(on,{kf1.frame},{kf2.frame})"
            
            parts.append(f"if({condition},{lerp}")
        
        # Final position
        final_kf = self.keyframes[-1]
        final_x = f"({final_kf.center_x}-(iw/zoom)/2)"
        
        expr = ""
        for part in parts:
            expr += part + ","
        expr += final_x
        expr += ")" * len(parts)
        
        return expr
    
    def _build_y_expression(self) -> str:
        """Build ffmpeg expression for y pan based on keyframes."""
        if len(self.keyframes) < 2:
            return f"(ih-ih/zoom)/2"
        
        parts = []
        for i in range(len(self.keyframes) - 1):
            kf1 = self.keyframes[i]
            kf2 = self.keyframes[i + 1]
            
            frame_diff = kf2.frame - kf1.frame
            if frame_diff == 0:
                continue
            
            progress = f"(on-{kf1.frame})/{frame_diff}"
            lerp = f"{kf1.center_y}+({kf2.center_y}-{kf1.center_y})*{progress}-(ih/zoom)/2"
            
            if i == 0:
                condition = f"lt(on,{kf2.frame})"
            else:
                condition = f"between(on,{kf1.frame},{kf2.frame})"
            
            parts.append(f"if({condition},{lerp}")
        
        final_kf = self.keyframes[-1]
        final_y = f"({final_kf.center_y}-(ih/zoom)/2)"
        
        expr = ""
        for part in parts:
            expr += part + ","
        expr += final_y
        expr += ")" * len(parts)
        
        return expr
    
    def get_total_duration(self) -> float:
        """Get total video duration in seconds."""
        if not self.keyframes:
            return 0
        return self.keyframes[-1].frame / self.fps
    
    def build_ffmpeg_command(self, output_path: str) -> List[str]:
        """Build the complete ffmpeg command."""
        zoom_expr = self._build_zoom_expression()
        x_expr = self._build_x_expression()
        y_expr = self._build_y_expression()
        
        total_frames = self.keyframes[-1].frame if self.keyframes else 1
        duration = total_frames / self.fps
        
        # Build zoompan filter
        zoompan_filter = (
            f"zoompan="
            f"z='{zoom_expr}':"
            f"x='{x_expr}':"
            f"y='{y_expr}':"
            f"d=1:"
            f"s={self.output_width}x{self.output_height}:"
            f"fps={self.fps}"
        )
        
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-loop', '1',
            '-i', self.image_path,
            '-vf', zoompan_filter,
            '-t', str(duration),
            '-pix_fmt', 'yuv420p',
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            output_path
        ]
        
        return cmd
    
    def generate(self, output_path: str, progress_callback=None) -> Tuple[bool, str]:
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
        
        cmd = self.build_ffmpeg_command(output_path)
        
        if progress_callback:
            progress_callback("Starting video generation...")
        
        try:
            # Run ffmpeg
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                return True, f"Video generated successfully: {output_path}"
            else:
                return False, f"FFmpeg error: {stderr}"
                
        except FileNotFoundError:
            return False, "FFmpeg not found. Please install FFmpeg."
        except Exception as e:
            return False, f"Error: {str(e)}"


def generate_video_from_snippets(
    image_path: str,
    snippets: List[dict],
    output_path: str,
    aspect_ratio: str = "9:16",
    progress_callback=None
) -> Tuple[bool, str]:
    """
    Convenience function to generate a Ken Burns video.
    
    Args:
        image_path: Path to source image
        snippets: List of snippet dicts with x, y, w, h keys
        output_path: Path for output video
        aspect_ratio: "9:16", "16:9", or "1:1"
        progress_callback: Optional callback for progress
    
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
                'height': rect.height()
            })
        elif 'w' in s:
            # Already in dict format with w/h
            normalized_snippets.append({
                'x': s['x'],
                'y': s['y'],
                'width': s['w'],
                'height': s['h']
            })
        else:
            normalized_snippets.append(s)
    
    generator = KenBurnsGenerator(
        image_path=image_path,
        snippets=normalized_snippets,
        output_width=width,
        output_height=height
    )
    
    return generator.generate(output_path, progress_callback)
