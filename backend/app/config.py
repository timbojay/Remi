import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the backend directory (parent of app/)
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env", override=True)


class Settings:
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    USER_NAME: str = os.getenv("USER_NAME", "Tim")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "claude-sonnet-4-20250514")
    DB_PATH: str = os.getenv("DB_PATH", str(_backend_dir / "data" / "remi.db"))
    HOST: str = "127.0.0.1"
    PORT: int = 8001


settings = Settings()
