"""Pydantic models for relay API."""

from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator, Field, Tag

from hoardicult.devices.relay_expander import RelayState

# --- Schedule models ---


class SingleSchedule(BaseModel):
    """One continuous block at a fixed start time."""

    mode: Literal["single"] = "single"
    total_minutes: int = Field(..., ge=1, le=1440)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class IntervalSchedule(BaseModel):
    """Evenly-spaced runs across 24 hours."""

    mode: Literal["interval"] = "interval"
    total_minutes: int = Field(..., ge=1, le=1440)
    interval_count: int = Field(..., ge=1, le=96)


class DawnDuskSchedule(BaseModel):
    """Half at dawn_time, half at dusk_time."""

    mode: Literal["dawn_dusk"] = "dawn_dusk"
    total_minutes: int = Field(..., ge=1, le=1440)
    dawn_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    dusk_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")


def _schedule_discriminator(v: dict | BaseModel) -> str:
    if isinstance(v, dict):
        return v.get("mode", "single")
    return getattr(v, "mode", "single")


RelaySchedule = Annotated[
    Annotated[SingleSchedule, Tag("single")]
    | Annotated[IntervalSchedule, Tag("interval")]
    | Annotated[DawnDuskSchedule, Tag("dawn_dusk")],
    Discriminator(_schedule_discriminator),
]


class RelayScheduleInfo(BaseModel):
    """Schedule state info included in health responses."""

    mode: str = Field(..., description="Schedule mode: single, interval, dawn_dusk")
    total_minutes: int = Field(..., description="Total minutes per day")
    next_on: str | None = Field(None, description="Next scheduled ON time (HH:MM)")
    next_off: str | None = Field(None, description="Next scheduled OFF time (HH:MM)")
    scheduled: bool = Field(
        default=False,
        description="True if scheduler is actively controlling this relay",
    )


# --- API / config models ---


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

    schedule_presets: dict[str, RelaySchedule] = Field(
        default_factory=dict, description="Named schedule presets"
    )
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


class ScheduleStatusResponse(BaseModel):
    """Response for GET /schedule."""

    presets: dict[str, dict] = Field(..., description="Available schedule presets")
    active_preset: str | None = Field(None, description="Currently active preset name")
    schedule_info: RelayScheduleInfo | None = Field(
        None, description="Active schedule details"
    )


class SetPresetRequest(BaseModel):
    """Request body for PUT /schedule."""

    active_preset: str | None = Field(
        None, description="Preset name or null to disable"
    )


class HealthResponse(BaseModel):
    """Full health response with relay states."""

    status: str = Field(default="ok", description="Service status")
    ioexpander_connected: bool = Field(..., description="IOExpander connection status")
    timestamp: str = Field(..., description="ISO timestamp for cache-busting")
    summary: SystemSummary = Field(..., description="System summary statistics")
    boards: list[BoardHealthInfo] = Field(
        ..., description="All boards with relay states"
    )
    active_schedule: RelayScheduleInfo | None = Field(
        None, description="Global active schedule info"
    )
