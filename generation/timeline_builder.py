"""
Timeline Builder Module

Constructs the video timeline with keyframes for snippets and sub-images.
Handles interleaving of sub-images after their specified snippets.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class TimelineEvent:
    """Represents an event in the video timeline."""
    time: float  # Start time in seconds
    duration: float  # Duration in seconds
    event_type: str  # 'intro', 'snippet', 'sub_image', 'outro'
    
    # Camera position
    center_x: int = 0
    center_y: int = 0
    zoom: float = 1.0
    
    # Content info
    index: int = -1  # Index of snippet or sub-image
    content_id: str = ""  # ID for sub-images
    
    # Box overlay
    box_rect: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h) for box overlay
    
    # Audio
    audio_path: Optional[str] = None
    audio_duration: float = 0.0
    
    # Sub-image specific
    sub_image_visible: bool = False
    sub_image_rect: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)


@dataclass
class TimelineConfig:
    """Configuration for timeline building."""
    intro_duration: float = 2.0
    snippet_duration: float = 3.0  # Animation time to move to snippet
    hold_duration: float = 1.0  # Minimum hold time at snippet
    outro_duration: float = 2.0
    
    min_zoom: float = 1.0
    max_zoom: float = 4.0
    
    use_zoom: bool = True  # If False, zoom stays at 1.0
    use_ken_burns: bool = True  # If False, instant cuts instead of smooth


class TimelineBuilder:
    """
    Builds the video timeline with proper ordering of snippets and sub-images.
    
    Timeline structure:
    - Intro (overview)
    - For each snippet:
        - Transition to snippet
        - Hold at snippet (play audio)
        - Any sub-images that appear after this snippet
    - Outro (back to overview)
    """
    
    def __init__(
        self,
        image_width: int,
        image_height: int,
        config: TimelineConfig = None
    ):
        self.image_width = image_width
        self.image_height = image_height
        self.config = config or TimelineConfig()
        
        # Center of image for overview shots
        self.center_x = image_width // 2
        self.center_y = image_height // 2
    
    def build(
        self,
        snippets: List[dict],
        sub_images: List[dict] = None
    ) -> List[TimelineEvent]:
        """
        Build the complete timeline.
        
        Args:
            snippets: List of snippet dicts with x, y, width, height, audio_path, audio_duration
            sub_images: List of sub-image dicts with position, size, after_snip, audio_path, etc.
        
        Returns:
            List of TimelineEvent objects in chronological order
        """
        events = []
        current_time = 0.0
        sub_images = sub_images or []
        
        # Group sub-images by after_snip
        sub_images_by_snippet = {}
        for si in sub_images:
            after_idx = si.get('after_snip', 0)
            if after_idx not in sub_images_by_snippet:
                sub_images_by_snippet[after_idx] = []
            sub_images_by_snippet[after_idx].append(si)
        
        # Track which sub-images are currently visible (for persistent ones)
        visible_sub_images = []
        
        # === INTRO ===
        events.append(TimelineEvent(
            time=current_time,
            duration=self.config.intro_duration,
            event_type='intro',
            center_x=self.center_x,
            center_y=self.center_y,
            zoom=1.0
        ))
        current_time += self.config.intro_duration
        
        # === SNIPPETS with interleaved sub-images ===
        for i, snippet in enumerate(snippets):
            # Get snippet dimensions
            sx = snippet.get('x', 0)
            sy = snippet.get('y', 0)
            sw = snippet.get('width', snippet.get('w', 100))
            sh = snippet.get('height', snippet.get('h', 100))
            s_audio_path = snippet.get('audio_path')
            s_audio_dur = snippet.get('audio_duration', 0.0)
            
            # Calculate zoom and center for this snippet
            if self.config.use_zoom:
                snippet_zoom = self._calculate_zoom(sw, sh, padding=0.8)
            else:
                snippet_zoom = 1.0
            
            snippet_center_x = sx + sw // 2
            snippet_center_y = sy + sh // 2
            
            # Transition duration (0 if no Ken Burns)
            trans_duration = self.config.snippet_duration if self.config.use_ken_burns else 0.0
            
            # Hold duration (max of audio or minimum hold)
            hold_duration = max(s_audio_dur, self.config.hold_duration)
            
            # Create snippet event
            events.append(TimelineEvent(
                time=current_time,
                duration=trans_duration + hold_duration,
                event_type='snippet',
                center_x=snippet_center_x if self.config.use_zoom else self.center_x,
                center_y=snippet_center_y if self.config.use_zoom else self.center_y,
                zoom=snippet_zoom,
                index=i,
                box_rect=(sx, sy, sw, sh),
                audio_path=s_audio_path,
                audio_duration=s_audio_dur
            ))
            
            current_time += trans_duration + hold_duration
            
            # Add sub-images that appear after this snippet
            if i in sub_images_by_snippet:
                for si in sub_images_by_snippet[i]:
                    current_time = self._add_sub_image_event(
                        events, si, current_time, visible_sub_images
                    )
        
        # === OUTRO ===
        outro_duration = self.config.outro_duration if self.config.use_ken_burns else 0.0
        events.append(TimelineEvent(
            time=current_time,
            duration=outro_duration,
            event_type='outro',
            center_x=self.center_x,
            center_y=self.center_y,
            zoom=1.0
        ))
        
        return events
    
    def _add_sub_image_event(
        self,
        events: List[TimelineEvent],
        sub_img: dict,
        current_time: float,
        visible_sub_images: List[dict]
    ) -> float:
        """Add a sub-image event to the timeline."""
        pos = sub_img.get('position', (0, 0))
        size = sub_img.get('size', (100, 100))
        si_x, si_y = int(pos[0]), int(pos[1])
        si_w, si_h = int(size[0]), int(size[1])
        
        audio_path = sub_img.get('audio_path')
        audio_dur = sub_img.get('audio_duration', 0.0)
        persistent = sub_img.get('persistent', False)
        
        # Calculate zoom and center for sub-image (if zoom mode)
        if self.config.use_zoom:
            si_zoom = self._calculate_zoom(si_w, si_h, padding=0.6)
            si_center_x = si_x + si_w // 2
            si_center_y = si_y + si_h // 2
        else:
            si_zoom = 1.0
            si_center_x = self.center_x
            si_center_y = self.center_y
        
        # Transition duration
        trans_duration = self.config.snippet_duration if self.config.use_ken_burns else 0.0
        
        # Hold duration
        hold_duration = max(audio_dur, self.config.hold_duration)
        
        # Track visibility
        visible_sub_images.append({
            'id': sub_img.get('id', ''),
            'rect': (si_x, si_y, si_w, si_h),
            'persistent': persistent,
            'start_time': current_time,
            'end_time': None if persistent else current_time + trans_duration + hold_duration
        })
        
        events.append(TimelineEvent(
            time=current_time,
            duration=trans_duration + hold_duration,
            event_type='sub_image',
            center_x=si_center_x,
            center_y=si_center_y,
            zoom=si_zoom,
            content_id=sub_img.get('id', ''),
            box_rect=None,  # Sub-images don't get box overlay
            sub_image_visible=True,
            sub_image_rect=(si_x, si_y, si_w, si_h),
            audio_path=audio_path,
            audio_duration=audio_dur
        ))
        
        return current_time + trans_duration + hold_duration
    
    def _calculate_zoom(self, width: int, height: int, padding: float = 0.8) -> float:
        """Calculate optimal zoom to fit a region in viewport."""
        zoom_x = (self.image_width * padding) / width
        zoom_y = (self.image_height * padding) / height
        zoom = min(zoom_x, zoom_y)
        return max(self.config.min_zoom, min(self.config.max_zoom, zoom))
    
    def get_total_duration(self, events: List[TimelineEvent]) -> float:
        """Get total duration of the timeline."""
        if not events:
            return 0.0
        last = events[-1]
        return last.time + last.duration
    
    def get_visible_sub_images_at_time(
        self,
        t: float,
        sub_images: List[dict],
        events: List[TimelineEvent]
    ) -> List[dict]:
        """
        Get list of sub-images that should be visible at time t.
        
        For persistent sub-images: visible from their start time until video end
        For non-persistent: visible only during their event
        """
        visible = []
        total_duration = self.get_total_duration(events)
        
        # Find when each sub-image starts
        sub_image_starts = {}
        for event in events:
            if event.event_type == 'sub_image':
                sub_image_starts[event.content_id] = event.time
        
        for si in sub_images:
            si_id = si.get('id', '')
            start_time = sub_image_starts.get(si_id, 0)
            persistent = si.get('persistent', False)
            audio_dur = si.get('audio_duration', 0.0)
            
            if persistent:
                # Visible from start_time until video end
                if t >= start_time:
                    visible.append(si)
            else:
                # Visible only during its event duration
                # Find the matching event
                for event in events:
                    if event.event_type == 'sub_image' and event.content_id == si_id:
                        if event.time <= t <= event.time + event.duration:
                            visible.append(si)
                        break
        
        return visible
