"""Configuration constants for the RPS game."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = BASE_DIR / "models" / "rps_yolov8n.pt"
DATABASE_PATH = Path(__file__).resolve().parent / "game_history.db"

COUNTDOWN_SECONDS = 3
RESULT_DISPLAY_SECONDS = 2
ROUND_COOLDOWN_SECONDS = 1
CONFIDENCE_THRESHOLD = 0.3

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 640
CAMERA_FPS = 30

WS_FRAME_QUALITY = 85

MARKOV_ORDER = 3
HISTORY_WINDOW = 50
FREQUENCY_DECAY = 0.85
RECENT_WINDOW = 10
META_WINDOW = 20
