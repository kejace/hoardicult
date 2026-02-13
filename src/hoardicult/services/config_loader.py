"""Configuration loading utilities."""

import json
from pathlib import Path

from hoardicult.models.relay import BoardsConfig, RelaySchedule


def load_boards_config(
    config_path: str | Path,
) -> tuple[list[dict], dict[str, RelaySchedule]]:
    """Load board configurations and schedule presets from JSON file.

    Args:
        config_path: Path to boards.json configuration file

    Returns:
        Tuple of (board config dicts, schedule presets dict)

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid
    """
    path = Path(config_path)

    if not path.exists():
        return [], {}

    with open(path) as f:
        data = json.load(f)

    config = BoardsConfig(**data)

    board_dicts = [board.model_dump() for board in config.boards]
    return board_dicts, config.schedule_presets
