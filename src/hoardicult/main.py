"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from hoardicult.api.boards import router as boards_router
from hoardicult.api.boards import set_board_configs, set_relay_controller
from hoardicult.core.config import settings
from hoardicult.devices.ioexpander import IOExpander, IOExpanderConnectionError
from hoardicult.devices.relay_expander import RelayController
from hoardicult.services.config_loader import load_boards_config

logger = logging.getLogger(__name__)

# Global instances (managed by lifespan)
ioexpander: IOExpander | None = None
relay_controller: RelayController | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle management."""
    global ioexpander, relay_controller

    # Load board configurations
    board_configs = load_boards_config(settings.boards_config_path)
    set_board_configs(board_configs)
    logger.info(f"Loaded {len(board_configs)} board configurations")

    # Initialize IOExpander connection
    ioexpander = IOExpander(
        port=settings.serial_port,
        baudrate=settings.serial_baudrate,
    )

    try:
        ioexpander.connect()
        logger.info(f"Connected to IOExpander on {settings.serial_port}")
    except IOExpanderConnectionError as e:
        logger.warning(f"Could not connect to IOExpander: {e}")
        logger.warning("Running in disconnected mode - relay commands will fail")

    # Initialize relay controller
    relay_controller = RelayController(ioexpander)
    set_relay_controller(relay_controller)

    # Configure RelayExpander counts for each board
    if ioexpander.is_connected:
        for config in board_configs:
            board_addr = config["board_addr"]
            count = config.get("relay_expander_count", 1)
            try:
                await relay_controller.set_relay_expander_count(board_addr, count)
                logger.info(
                    f"Board {board_addr}: configured {count} RelayExpander(s)"
                )
            except Exception as e:
                logger.error(f"Failed to configure board {board_addr}: {e}")

    yield

    # Shutdown: close all valves for safety
    if ioexpander.is_connected and relay_controller:
        logger.info("Shutting down: closing all valves")
        for config in board_configs:
            board_addr = config["board_addr"]
            relay_count = config.get("relay_count", 16)
            try:
                await relay_controller.close_all_on_board(board_addr, relay_count)
            except Exception as e:
                logger.error(f"Error closing valves on board {board_addr}: {e}")

    # Disconnect
    if ioexpander:
        ioexpander.disconnect()
        logger.info("Disconnected from IOExpander")


app = FastAPI(
    title="Hoardicult",
    description="Plant watering controller with IOExpander integration",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(boards_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    connected = ioexpander.is_connected if ioexpander else False
    return {
        "status": "ok",
        "ioexpander_connected": str(connected).lower(),
    }
