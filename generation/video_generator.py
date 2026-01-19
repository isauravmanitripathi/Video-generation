"""
Ken Burns Video Generator - Main Module

Orchestrates video generation using modular components:
- timeline_builder: Constructs event timeline
- frame_renderer: Renders individual frames
- audio_mixer: Handles audio composition
- sub_image_handler: Processes sub-image overlays
"""

import os
from typing import List, Tuple, Callable
from PIL import Image
from moviepy import VideoClip

from generation.timeline_builder import TimelineBuilder, TimelineConfig, TimelineEvent
from generation.frame_renderer import ZoomRenderer, StaticRenderer
from generation.audio_mixer import AudioMixer
from generation.sub_image_handler import SubImageProcessor


class KenBurnsGenerator:
    """
    Main video generator class.
    
    Supports multiple rendering modes:
    - Zoom + Ken Burns: Smooth camera pan/zoom to snippets
    - Zoom Only: Instant cuts to zoomed snippets
    - Static Full: Full image with box overlays
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
        use_zoom: bool = True,
        sub_images: List[dict] = None
    ):
        self.image_path = image_path
        self.output_width = output_width
        self.output_height = output_height
        self.fps = fps
        self.ken_burns = ken_burns
        self.use_zoom = use_zoom
        self.show_boxes = show_boxes
        self.box_color = box_color
        self.box_thickness = box_thickness
        self.snippets = snippets
        self.sub_images = sub_images or []
        
        # Load source image
        self.original_image = Image.open(image_path).convert('RGBA')
        self.image_width, self.image_height = self.original_image.size
        
        # Process sub-images
        self.sub_image_processor = SubImageProcessor(self.original_image, self.sub_images)
        self.composited_image = self.sub_image_processor.composite_all()
        
        # Build timeline config
        # If no zoom, Ken Burns is automatically disabled
        if not use_zoom:
            ken_burns = False
        
        self.timeline_config = TimelineConfig(
            intro_duration=intro_duration,
            snippet_duration=snippet_duration if ken_burns else 0.0,
            hold_duration=hold_duration,
            outro_duration=outro_duration if ken_burns else 0.0,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            use_zoom=use_zoom,
            use_ken_burns=ken_burns
        )
        
        # Build timeline
        self.timeline_builder = TimelineBuilder(
            self.image_width,
            self.image_height,
            self.timeline_config
        )
        self.events = self.timeline_builder.build(snippets, self.sub_images)
        
        # Print timeline for debugging
        self._print_timeline()
        
        # Create renderer based on mode
        if use_zoom:
            self.renderer = ZoomRenderer(
                source_image=self.composited_image,
                output_width=output_width,
                output_height=output_height,
                show_boxes=show_boxes,
                box_color=box_color,
                box_thickness=box_thickness,
                use_ken_burns=ken_burns
            )
        else:
            # Static renderer shows full image with box overlays
            self.renderer = StaticRenderer(
                source_image=self.original_image,  # Use original, sub-images rendered separately
                output_width=output_width,
                output_height=output_height,
                show_boxes=True,  # Always show boxes in static mode
                box_color=box_color,
                box_thickness=box_thickness,
                sub_images=self.sub_images
            )
        
        # Audio mixer
        self.audio_mixer = AudioMixer()
    
    def _print_timeline(self):
        """Print timeline for debugging."""
        print("\n=== Video Timeline ===")
        for event in self.events:
            sub_info = ""
            if event.event_type == 'sub_image':
                sub_info = f" (id={event.content_id})"
            print(f"  {event.time:.2f}s - {event.event_type}{sub_info} @ ({event.center_x}, {event.center_y}) zoom={event.zoom:.2f}")
        print(f"  Total duration: {self.get_total_duration():.2f}s")
        print("======================\n")
    
    def get_total_duration(self) -> float:
        """Get total video duration."""
        return self.timeline_builder.get_total_duration(self.events)
    
    def _render_frame(self, t: float) -> 'np.ndarray':
        """Render a frame at time t."""
        # Get visible sub-images at this time
        visible_sub_images = self.timeline_builder.get_visible_sub_images_at_time(
            t, self.sub_images, self.events
        )
        
        return self.renderer.render_frame(t, self.events, visible_sub_images)
    
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
            
            # Create video clip
            video = VideoClip(lambda t: self._render_frame(t), duration=total_duration).with_fps(self.fps)
            
            # Add audio
            if progress_callback:
                progress_callback("Adding audio...")
            
            composite_audio = self.audio_mixer.create_composite_audio(self.events)
            if composite_audio:
                video = video.with_audio(composite_audio)
            
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
                logger=None
            )
            
            # Cleanup
            video.close()
            self.audio_mixer.cleanup(composite_audio)
            
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
    use_zoom: bool = True,
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
        ken_burns: Whether to use Ken Burns animation (smooth) or instant cuts
        use_zoom: Whether to zoom to snippets or show full image
        progress_callback: Optional callback for progress
        sub_images: List of sub-image overlay dicts
    
    Returns:
        Tuple of (success, message)
    """
    # Determine output dimensions
    if "9:16" in aspect_ratio:
        width, height = 1080, 1920
    elif "16:9" in aspect_ratio:
        width, height = 1920, 1080
    else:
        width, height = 1080, 1080
    
    # Normalize snippet format
    normalized_snippets = []
    for s in snippets:
        if 'source_rect' in s:
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
        use_zoom=use_zoom,
        sub_images=sub_images or []
    )
    
    return generator.generate(output_path, progress_callback)
