"""Application configuration."""

import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    """Application settings loaded from environment."""

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./hoardicult.db")
    serial_port: str = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
    serial_baudrate: int = int(os.getenv("SERIAL_BAUDRATE", "115200"))
    boards_config_path: str = os.getenv("BOARDS_CONFIG_PATH", "boards.json")


settings = Settings()
