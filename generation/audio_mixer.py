"""
Audio Mixer Module

Handles audio composition for the video:
- Loads audio clips from snippets and sub-images
- Positions them at correct timeline points
- Creates composite audio track
"""

import os
from typing import List, Optional, Tuple
from generation.timeline_builder import TimelineEvent


class AudioMixer:
    """
    Mixes audio from snippets and sub-images into a composite track.
    """
    
    def __init__(self):
        self.audio_clips = []
    
    def build_audio_clips(self, events: List[TimelineEvent]) -> List[Tuple[str, float]]:
        """
        Build list of audio clips with their start times.
        
        Args:
            events: List of TimelineEvent objects
        
        Returns:
            List of (audio_path, start_time) tuples
        """
        clips = []
        
        for event in events:
            if event.audio_path and os.path.exists(event.audio_path):
                # Audio starts at the beginning of the event
                clips.append((event.audio_path, event.time))
        
        return clips
    
    def create_composite_audio(self, events: List[TimelineEvent]):
        """
        Create a MoviePy CompositeAudioClip from timeline events.
        
        Returns the composite audio clip or None if no audio.
        """
        from moviepy import AudioFileClip, CompositeAudioClip
        
        clips = self.build_audio_clips(events)
        
        if not clips:
            return None
        
        audio_clips = []
        for audio_path, start_time in clips:
            try:
                audio = AudioFileClip(audio_path)
                audio = audio.with_start(start_time)
                audio_clips.append(audio)
                print(f"Audio: {os.path.basename(audio_path)} at {start_time:.2f}s")
            except Exception as e:
                print(f"Failed to load audio {audio_path}: {e}")
        
        if audio_clips:
            return CompositeAudioClip(audio_clips)
        
        return None
    
    def cleanup(self, composite_audio):
        """Clean up audio clips."""
        if composite_audio and hasattr(composite_audio, 'clips'):
            for clip in composite_audio.clips:
                try:
                    clip.close()
                except:
                    pass
