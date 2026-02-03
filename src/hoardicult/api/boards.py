"""FastAPI endpoints for board and relay control."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

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


@router.post("/{board_addr}/demo")
async def demo_board(
    board_addr: BoardAddrPath,
    controller: RelayControllerDep,
    delay_ms: int = Query(default=100, ge=10, le=2000),
    cycles: int = Query(default=1, ge=1, le=10),
) -> dict:
    """Run running-light demo on a single board.

    Creates a wave effect across the relay LEDs by turning on each relay
    sequentially while turning off the previous one.

    Args:
        board_addr: Board address to run demo on
        delay_ms: Delay between steps in milliseconds (10-2000)
        cycles: Number of times to repeat the pattern (1-10)

    Returns:
        Status message with demo parameters
    """
    config = get_board_config(board_addr)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board {board_addr} not found",
        )

    relay_count = config.get("relay_count", 16)

    try:
        for _ in range(cycles):
            await controller.run_demo(board_addr, relay_count, delay_ms)
    except IOExpanderError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Communication error: {e}",
        )

    return {
        "status": "completed",
        "board_addr": board_addr,
        "relay_count": relay_count,
        "delay_ms": delay_ms,
        "cycles": cycles,
    }


@router.post("/demo")
async def demo_all_boards(
    controller: RelayControllerDep,
    delay_ms: int = Query(default=100, ge=10, le=2000),
    cycles: int = Query(default=1, ge=1, le=10),
) -> dict:
    """Run running-light demo on all boards sequentially.

    Runs the running-light pattern on each configured board one after another.

    Args:
        delay_ms: Delay between steps in milliseconds (10-2000)
        cycles: Number of times to repeat the pattern per board (1-10)

    Returns:
        Status message with demo results for each board
    """
    results = []
    errors = []

    for config in _board_configs:
        board_addr = config["board_addr"]
        relay_count = config.get("relay_count", 16)
        try:
            for _ in range(cycles):
                await controller.run_demo(board_addr, relay_count, delay_ms)
            results.append({
                "board_addr": board_addr,
                "status": "completed",
                "relay_count": relay_count,
            })
        except IOExpanderError as e:
            errors.append(f"Board {board_addr}: {e}")
            results.append({
                "board_addr": board_addr,
                "status": "error",
                "error": str(e),
            })

    if errors:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Some boards had errors during demo",
                "errors": errors,
                "results": results,
            },
        )

    return {
        "status": "completed",
        "delay_ms": delay_ms,
        "cycles": cycles,
        "boards": results,
    }
