"""Configuration loading utilities."""

import json
from pathlib import Path

from hoardicult.models.relay import BoardsConfig


def load_boards_config(config_path: str | Path) -> list[dict]:
    """Load board configurations from JSON file.

    Args:
        config_path: Path to boards.json configuration file

    Returns:
        List of board configuration dictionaries

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid
    """
    path = Path(config_path)

    if not path.exists():
        # Return empty config if file doesn't exist (allows testing without config)
        return []

    with open(path) as f:
        data = json.load(f)

    # Validate with Pydantic
    config = BoardsConfig(**data)

    return [board.model_dump() for board in config.boards]
