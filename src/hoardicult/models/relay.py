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


# Health endpoint models


class RelayStateInfo(BaseModel):
    """Compact relay state info for health response."""

    relay_num: int = Field(..., ge=1, le=256, description="Relay number")
    state: RelayState = Field(..., description="Current relay state")
    simulated: bool = Field(
        default=False, description="True if state is simulated (not on hardware)"
    )


class BoardHealthInfo(BaseModel):
    """Board info with relay states for health response."""

    board_addr: int = Field(..., ge=1, le=255, description="IOExpander board address")
    name: str = Field(default="", description="Human-readable board name")
    relay_count: int = Field(default=16, ge=1, le=256, description="Total relays")
    relays: list[RelayStateInfo] = Field(
        default_factory=list, description="Relay states"
    )


class SystemSummary(BaseModel):
    """Summary statistics for the system."""

    total_boards: int = Field(..., description="Number of configured boards")
    total_relays: int = Field(..., description="Total relay count across all boards")
    relays_on: int = Field(..., description="Number of relays currently ON")
    relays_off: int = Field(..., description="Number of relays currently OFF")
    relays_unknown: int = Field(..., description="Number of relays in unknown state")


class HealthResponse(BaseModel):
    """Full health response with relay states."""

    status: str = Field(default="ok", description="Service status")
    ioexpander_connected: bool = Field(..., description="IOExpander connection status")
    timestamp: str = Field(..., description="ISO timestamp for cache-busting")
    summary: SystemSummary = Field(..., description="System summary statistics")
    boards: list[BoardHealthInfo] = Field(
        ..., description="All boards with relay states"
    )
