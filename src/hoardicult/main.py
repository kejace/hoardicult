"""FastAPI application entry point."""

import logging
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hoardicult.api.boards import router as boards_router
from hoardicult.api.boards import set_board_configs, set_relay_controller
from hoardicult.core.config import settings
from hoardicult.devices.ioexpander import IOExpander, IOExpanderConnectionError
from hoardicult.devices.relay_expander import RelayController, RelayState
from hoardicult.models.relay import (
    BoardHealthInfo,
    HealthResponse,
    RelayStateInfo,
    SystemSummary,
)
from hoardicult.services.config_loader import load_boards_config
from hoardicult.services.ws_manager import ConnectionManager

logger = logging.getLogger(__name__)

# Global instances (managed by lifespan)
ioexpander: IOExpander | None = None
relay_controller: RelayController | None = None
board_configs: list[dict] = []
ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle management."""
    global ioexpander, relay_controller, board_configs

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

    # Initialize relay controller with WebSocket broadcast callback
    relay_controller = RelayController(ioexpander, on_state_change=broadcast_state)
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

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"

app.include_router(boards_router)


def _build_health_snapshot() -> dict:
    """Build the health snapshot dict (shared by /health and WebSocket broadcast)."""
    connected = ioexpander.is_connected if ioexpander else False

    boards_health: list[dict] = []
    total_relays = 0
    relays_on = 0
    relays_off = 0
    relays_unknown = 0

    for config in board_configs:
        board_addr = config["board_addr"]
        relay_count = config.get("relay_count", 16)
        total_relays += relay_count

        relays: list[dict] = []
        for relay_num in range(1, relay_count + 1):
            if relay_controller:
                state = relay_controller.get_relay_state(board_addr, relay_num)
                simulated = relay_controller.is_simulated(board_addr, relay_num)
            else:
                state = RelayState.UNKNOWN
                simulated = False

            relays.append(
                {"relay_num": relay_num, "state": state.value, "simulated": simulated}
            )

            if state == RelayState.ON:
                relays_on += 1
            elif state == RelayState.OFF:
                relays_off += 1
            else:
                relays_unknown += 1

        boards_health.append(
            {
                "board_addr": board_addr,
                "name": config.get("name", ""),
                "relay_count": relay_count,
                "relays": relays,
            }
        )

    return {
        "status": "ok",
        "ioexpander_connected": connected,
        "timestamp": datetime.now(UTC).isoformat(),
        "summary": {
            "total_boards": len(board_configs),
            "total_relays": total_relays,
            "relays_on": relays_on,
            "relays_off": relays_off,
            "relays_unknown": relays_unknown,
        },
        "boards": boards_health,
    }


async def broadcast_state() -> None:
    """Build health snapshot and broadcast to all WebSocket clients."""
    await ws_manager.broadcast(_build_health_snapshot())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time state updates."""
    await ws_manager.connect(websocket)
    try:
        # Send initial state
        await websocket.send_json(_build_health_snapshot())
        # Keep connection alive until client disconnects
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/version")
async def version() -> dict:
    """Return the current git commit hash."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent,
            text=True,
        ).strip()
    except Exception:
        commit = "unknown"
    return {"commit": commit}


@app.get("/", include_in_schema=False)
async def serve_dashboard() -> FileResponse:
    """Serve the dashboard HTML page."""
    return FileResponse(STATIC_DIR / "index.html")


# Mount static files (must be after specific routes)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint with full relay state information."""
    connected = ioexpander.is_connected if ioexpander else False

    # Build board health info with relay states
    boards_health: list[BoardHealthInfo] = []
    total_relays = 0
    relays_on = 0
    relays_off = 0
    relays_unknown = 0

    for config in board_configs:
        board_addr = config["board_addr"]
        relay_count = config.get("relay_count", 16)
        total_relays += relay_count

        relays: list[RelayStateInfo] = []
        for relay_num in range(1, relay_count + 1):
            if relay_controller:
                state = relay_controller.get_relay_state(board_addr, relay_num)
                simulated = relay_controller.is_simulated(board_addr, relay_num)
            else:
                state = RelayState.UNKNOWN
                simulated = False

            relays.append(
                RelayStateInfo(relay_num=relay_num, state=state, simulated=simulated)
            )

            if state == RelayState.ON:
                relays_on += 1
            elif state == RelayState.OFF:
                relays_off += 1
            else:
                relays_unknown += 1

        boards_health.append(
            BoardHealthInfo(
                board_addr=board_addr,
                name=config.get("name", ""),
                relay_count=relay_count,
                relays=relays,
            )
        )

    summary = SystemSummary(
        total_boards=len(board_configs),
        total_relays=total_relays,
        relays_on=relays_on,
        relays_off=relays_off,
        relays_unknown=relays_unknown,
    )

    return HealthResponse(
        status="ok",
        ioexpander_connected=connected,
        timestamp=datetime.now(UTC).isoformat(),
        summary=summary,
        boards=boards_health,
    )
