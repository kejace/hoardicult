"""Pydantic models for relay API."""

from pydantic import BaseModel, Field

from hoardicult.devices.relay_expander import RelayState


class RelayResponse(BaseModel):
    """API response for a single relay state."""

    board_addr: int = Field(..., ge=1, le=255, description="IOExpander board address")
    relay_num: int = Field(..., ge=1, le=256, description="Relay number")
    state: RelayState = Field(..., description="Current relay state")


class BoardConfig(BaseModel):
    """Configuration for a single IOExpander board."""

    board_addr: int = Field(..., ge=1, le=255, description="IOExpander board address")
    name: str = Field(default="", description="Human-readable board name")
    relay_expander_count: int = Field(
        default=1, ge=1, le=16, description="Number of RelayExpander boards"
    )
    relay_count: int = Field(
        default=16, ge=1, le=256, description="Total relays on this board"
    )


class BoardInfo(BaseModel):
    """API response for board information."""

    board_addr: int
    name: str
    relay_count: int
    relay_expander_count: int


class BoardListResponse(BaseModel):
    """API response listing all boards."""

    boards: list[BoardInfo]


class RelayListResponse(BaseModel):
    """API response listing relays on a board."""

    board_addr: int
    relays: list[RelayResponse]


class BoardsConfig(BaseModel):
    """Root configuration for all boards."""

    boards: list[BoardConfig]
