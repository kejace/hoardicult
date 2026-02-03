"""FastAPI endpoints for board and relay control."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from hoardicult.devices.ioexpander import IOExpanderError
from hoardicult.devices.relay_expander import RelayController, RelayState
from hoardicult.models.relay import (
    BoardInfo,
    BoardListResponse,
    RelayListResponse,
    RelayResponse,
)

router = APIRouter(prefix="/boards", tags=["boards"])


# These will be set by the application lifespan handler
_relay_controller: RelayController | None = None
_board_configs: list[dict] = []


def set_relay_controller(controller: RelayController) -> None:
    """Set the relay controller instance (called from main.py lifespan)."""
    global _relay_controller
    _relay_controller = controller


def set_board_configs(configs: list[dict]) -> None:
    """Set the board configurations (called from main.py lifespan)."""
    global _board_configs
    _board_configs = configs


def get_relay_controller() -> RelayController:
    """Dependency to get relay controller instance."""
    if _relay_controller is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Relay controller not initialized",
        )
    return _relay_controller


def get_board_config(board_addr: int) -> dict | None:
    """Get configuration for a specific board."""
    for config in _board_configs:
        if config["board_addr"] == board_addr:
            return config
    return None


RelayControllerDep = Annotated[RelayController, Depends(get_relay_controller)]

BoardAddrPath = Annotated[int, Path(ge=1, le=255, description="Board address")]
RelayNumPath = Annotated[int, Path(ge=1, le=256, description="Relay number")]


@router.get("", response_model=BoardListResponse)
async def list_boards() -> BoardListResponse:
    """List all configured IOExpander boards."""
    boards = [
        BoardInfo(
            board_addr=config["board_addr"],
            name=config.get("name", ""),
            relay_count=config.get("relay_count", 16),
            relay_expander_count=config.get("relay_expander_count", 1),
        )
        for config in _board_configs
    ]
    return BoardListResponse(boards=boards)


@router.get("/{board_addr}", response_model=BoardInfo)
async def get_board(board_addr: BoardAddrPath) -> BoardInfo:
    """Get information about a specific board."""
    config = get_board_config(board_addr)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board {board_addr} not found",
        )
    return BoardInfo(
        board_addr=config["board_addr"],
        name=config.get("name", ""),
        relay_count=config.get("relay_count", 16),
        relay_expander_count=config.get("relay_expander_count", 1),
    )


@router.get("/{board_addr}/relays", response_model=RelayListResponse)
async def list_relays(
    board_addr: BoardAddrPath,
    controller: RelayControllerDep,
) -> RelayListResponse:
    """List all relays and their states on a board."""
    config = get_board_config(board_addr)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board {board_addr} not found",
        )

    relay_count = config.get("relay_count", 16)
    relays = [
        RelayResponse(
            board_addr=board_addr,
            relay_num=i,
            state=controller.get_relay_state(board_addr, i),
        )
        for i in range(1, relay_count + 1)
    ]
    return RelayListResponse(board_addr=board_addr, relays=relays)


@router.get("/{board_addr}/relays/{relay_num}", response_model=RelayResponse)
async def get_relay(
    board_addr: BoardAddrPath,
    relay_num: RelayNumPath,
    controller: RelayControllerDep,
) -> RelayResponse:
    """Get the state of a specific relay."""
    config = get_board_config(board_addr)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board {board_addr} not found",
        )

    relay_count = config.get("relay_count", 16)
    if relay_num > relay_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relay {relay_num} not found on board {board_addr}",
        )

    return RelayResponse(
        board_addr=board_addr,
        relay_num=relay_num,
        state=controller.get_relay_state(board_addr, relay_num),
    )


@router.post("/{board_addr}/relays/{relay_num}/open", response_model=RelayResponse)
async def open_relay(
    board_addr: BoardAddrPath,
    relay_num: RelayNumPath,
    controller: RelayControllerDep,
) -> RelayResponse:
    """Open a relay (turn ON solenoid valve)."""
    config = get_board_config(board_addr)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board {board_addr} not found",
        )

    try:
        await controller.relay_on(board_addr, relay_num)
    except IOExpanderError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Communication error: {e}",
        )

    return RelayResponse(
        board_addr=board_addr,
        relay_num=relay_num,
        state=RelayState.ON,
    )


@router.post("/{board_addr}/relays/{relay_num}/close", response_model=RelayResponse)
async def close_relay(
    board_addr: BoardAddrPath,
    relay_num: RelayNumPath,
    controller: RelayControllerDep,
) -> RelayResponse:
    """Close a relay (turn OFF solenoid valve)."""
    config = get_board_config(board_addr)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board {board_addr} not found",
        )

    try:
        await controller.relay_off(board_addr, relay_num)
    except IOExpanderError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Communication error: {e}",
        )

    return RelayResponse(
        board_addr=board_addr,
        relay_num=relay_num,
        state=RelayState.OFF,
    )


@router.post("/{board_addr}/close-all", status_code=status.HTTP_204_NO_CONTENT)
async def close_all_on_board(
    board_addr: BoardAddrPath,
    controller: RelayControllerDep,
) -> None:
    """Emergency: Close all relays on a specific board."""
    config = get_board_config(board_addr)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board {board_addr} not found",
        )

    relay_count = config.get("relay_count", 16)
    try:
        await controller.close_all_on_board(board_addr, relay_count)
    except IOExpanderError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Communication error: {e}",
        )


@router.post("/close-all", status_code=status.HTTP_204_NO_CONTENT)
async def close_all_system(controller: RelayControllerDep) -> None:
    """Emergency: Close all relays on all boards."""
    errors = []
    for config in _board_configs:
        board_addr = config["board_addr"]
        relay_count = config.get("relay_count", 16)
        try:
            await controller.close_all_on_board(board_addr, relay_count)
        except IOExpanderError as e:
            errors.append(f"Board {board_addr}: {e}")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Errors during shutdown: {'; '.join(errors)}",
        )
