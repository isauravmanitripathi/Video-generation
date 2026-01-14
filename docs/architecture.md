# Video Content Generator Architecture

## Overview
This application generates short-form video content (Reels, Shorts) from text input using Edge TTS for audio and programmatic video assembly.

## Directory Structure
- **`gui/`**: Contains all PyQt5 widgets and windows.
- **`audio/`**: Handles Text-to-Speech operations (currently using edge-tts).
- **`processing/`**: Handles visual asset manipulation (ffmpeg, imaging).
- **`generation/`**: Orchestrates the flow: Text -> Audio -> Visuals -> Final Video.
- **`main.py`**: Application entry point.

## Workflows
1. User selects Aspect Ratio (9:16, 16:9, 1:1).
2. User inputs text and selects voice.
3. Generator module coordinates creation of audio and video assets.
