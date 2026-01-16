import asyncio
import subprocess
import os
import shutil
from typing import Optional, Tuple

class TTSHandler:
    """Handles Text-to-Speech generation using edge-tts."""
    
    def __init__(self):
        self.ensure_ffmpeg()
        
    def ensure_ffmpeg(self):
        """Check if ffmpeg and ffprobe are available."""
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise RuntimeError("FFmpeg/FFprobe not found in PATH.")

    def get_audio_duration(self, file_path: str) -> float:
        """Get duration of audio file in seconds using ffprobe."""
        try:
            cmd = [
                'ffprobe', 
                '-v', 'error', 
                '-show_entries', 'format=duration', 
                '-of', 'default=noprint_wrappers=1:nokey=1', 
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"Error getting duration for {file_path}: {e}")
            return 0.0

    async def _generate_edge_tts(self, text: str, voice: str, output_path: str) -> bool:
        """Generate TTS using edge-tts library (async)."""
        import edge_tts
        
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            return True
        except Exception as e:
            print(f"Error generating TTS: {e}")
            return False

    def generate_audio(self, text: str, voice: str, output_path: str) -> Tuple[bool, float]:
        """
        Generate audio from text.
        Returns (success, duration).
        """
        if not text.strip():
            return False, 0.0
            
        try:
            # Run async function synchronously
            asyncio.run(self._generate_edge_tts(text, voice, output_path))
            
            if os.path.exists(output_path):
                duration = self.get_audio_duration(output_path)
                return True, duration
            return False, 0.0
            
        except Exception as e:
            print(f"TTS Generation failed: {e}")
            return False, 0.0

    @staticmethod
    def get_voices():
        """Return list of available voices (simplified for now)."""
        return [
            "en-US-AriaNeural",
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-GB-SoniaNeural",
            "en-GB-RyanNeural"
        ]
