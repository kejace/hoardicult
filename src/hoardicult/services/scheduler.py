"""Relay scheduling service.

Evaluates a single global schedule preset and automatically opens/closes
ALL relays based on time-of-day rules.
"""

import asyncio
import json
import logging
from datetime import datetime, time
from pathlib import Path

from hoardicult.devices.relay_expander import RelayController
from hoardicult.models.relay import (
    DawnDuskSchedule,
    IntervalSchedule,
    RelaySchedule,
    RelayScheduleInfo,
    SingleSchedule,
)

logger = logging.getLogger(__name__)

TICK_INTERVAL = 30  # seconds


class SchedulerService:
    """Background service that controls ALL relays based on a single global schedule."""

    def __init__(
        self,
        relay_controller: RelayController,
        board_configs: list[dict],
        schedule_presets: dict[str, RelaySchedule],
        state_path: Path,
    ) -> None:
        self._controller = relay_controller
        self._board_configs = board_configs
        self._presets = schedule_presets
        self._state_path = state_path
        self._task: asyncio.Task | None = None
        self._active_preset: str | None = None
        self._active_schedule: RelaySchedule | None = None
        # Set of (board_addr, relay_num) currently turned on by scheduler
        self._scheduler_active: set[tuple[int, int]] = set()
        self._load_state()

    def _load_state(self) -> None:
        """Load active preset from disk."""
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text())
                name = data.get("active_preset")
                if name and name in self._presets:
                    self._active_preset = name
                    self._active_schedule = self._presets[name]
                    logger.info(f"Restored active preset: {name}")
        except Exception:
            logger.warning("Failed to load schedule state, starting with no preset")

    def _save_state(self) -> None:
        """Persist active preset to disk."""
        try:
            self._state_path.write_text(
                json.dumps({"active_preset": self._active_preset})
            )
        except Exception:
            logger.exception("Failed to save schedule state")

    def start(self) -> None:
        """Start the scheduler background loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler and turn off any scheduler-controlled relays."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

        await self._turn_off_all_active()
        logger.info("Scheduler stopped")

    async def set_active_preset(self, name: str | None) -> None:
        """Switch to a named preset (or None to disable scheduling)."""
        # Turn off any currently active relays
        await self._turn_off_all_active()

        if name is None:
            self._active_preset = None
            self._active_schedule = None
        else:
            if name not in self._presets:
                raise ValueError(f"Unknown preset: {name}")
            self._active_preset = name
            self._active_schedule = self._presets[name]

        self._save_state()
        logger.info(f"Active preset set to: {name}")

    async def _turn_off_all_active(self) -> None:
        """Turn off all relays the scheduler has turned on."""
        for board_addr, relay_num in list(self._scheduler_active):
            try:
                if self._controller.is_connected:
                    await self._controller.relay_off(board_addr, relay_num)
                else:
                    await self._controller.relay_off_simulated(board_addr, relay_num)
            except Exception as e:
                logger.error(
                    f"Error stopping relay {relay_num} on board {board_addr}: {e}"
                )
        self._scheduler_active.clear()

    async def _loop(self) -> None:
        """Main scheduler loop — tick every TICK_INTERVAL seconds."""
        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(TICK_INTERVAL)

    async def _tick(self) -> None:
        """Evaluate the active schedule and issue relay commands for ALL relays."""
        now = datetime.now()
        current_time = now.time()

        if self._active_schedule is None:
            # No schedule active — turn off anything still on
            if self._scheduler_active:
                await self._turn_off_all_active()
            return

        should_on = _should_be_on(self._active_schedule, current_time)

        for config in self._board_configs:
            board_addr = config["board_addr"]
            relay_count = config.get("relay_count", 16)

            for relay_num in range(1, relay_count + 1):
                key = (board_addr, relay_num)

                if should_on and key not in self._scheduler_active:
                    logger.info(
                        f"Scheduler: turning ON relay {relay_num} on board {board_addr}"
                    )
                    try:
                        if self._controller.is_connected:
                            await self._controller.relay_on(board_addr, relay_num)
                        else:
                            await self._controller.relay_on_simulated(
                                board_addr, relay_num
                            )
                        self._scheduler_active.add(key)
                    except Exception as e:
                        logger.error(f"Scheduler relay_on failed: {e}")

                elif not should_on and key in self._scheduler_active:
                    logger.info(
                        "Scheduler: turning OFF relay %d on board %d",
                        relay_num,
                        board_addr,
                    )
                    try:
                        if self._controller.is_connected:
                            await self._controller.relay_off(board_addr, relay_num)
                        else:
                            await self._controller.relay_off_simulated(
                                board_addr, relay_num
                            )
                        self._scheduler_active.discard(key)
                    except Exception as e:
                        logger.error(f"Scheduler relay_off failed: {e}")

    def get_status(self) -> dict:
        """Return schedule status for the API."""
        presets_dict = {}
        for name, sched in self._presets.items():
            presets_dict[name] = sched.model_dump()

        schedule_info = None
        if self._active_schedule is not None:
            now = datetime.now().time()
            next_on, next_off = _next_on_off(self._active_schedule, now)
            schedule_info = RelayScheduleInfo(
                mode=self._active_schedule.mode,
                total_minutes=self._active_schedule.total_minutes,
                next_on=next_on,
                next_off=next_off,
                scheduled=bool(self._scheduler_active),
            ).model_dump()

        return {
            "presets": presets_dict,
            "active_preset": self._active_preset,
            "schedule_info": schedule_info,
        }

    def get_active_schedule_info(self) -> RelayScheduleInfo | None:
        """Return active schedule info for health response."""
        if self._active_schedule is None:
            return None
        now = datetime.now().time()
        next_on, next_off = _next_on_off(self._active_schedule, now)
        return RelayScheduleInfo(
            mode=self._active_schedule.mode,
            total_minutes=self._active_schedule.total_minutes,
            next_on=next_on,
            next_off=next_off,
            scheduled=bool(self._scheduler_active),
        )

    def is_relay_scheduled(self, board_addr: int, relay_num: int) -> bool:
        """Check if a relay is currently being controlled by the scheduler."""
        return (board_addr, relay_num) in self._scheduler_active


# --- Pure functions for schedule evaluation ---


def _parse_schedule(data: dict) -> RelaySchedule | None:
    """Parse a schedule dict into a typed model."""
    mode = data.get("mode")
    try:
        if mode == "single":
            return SingleSchedule(**data)
        elif mode == "interval":
            return IntervalSchedule(**data)
        elif mode == "dawn_dusk":
            return DawnDuskSchedule(**data)
    except Exception:
        logger.warning(f"Invalid schedule config: {data}")
    return None


def _parse_time(t: str) -> time:
    """Parse HH:MM string to time object."""
    h, m = t.split(":")
    return time(int(h), int(m))


def _time_to_minutes(t: time) -> int:
    """Convert time to minutes since midnight."""
    return t.hour * 60 + t.minute


def _should_be_on(schedule: RelaySchedule, now: time) -> bool:
    """Determine if the relay should be on at the given time."""
    if isinstance(schedule, SingleSchedule):
        return _check_single(schedule, now)
    elif isinstance(schedule, IntervalSchedule):
        return _check_interval(schedule, now)
    elif isinstance(schedule, DawnDuskSchedule):
        return _check_dawn_dusk(schedule, now)
    return False


def _check_single(schedule: SingleSchedule, now: time) -> bool:
    """Check if now falls within a single continuous block."""
    start = _parse_time(schedule.start_time)
    start_min = _time_to_minutes(start)
    end_min = start_min + schedule.total_minutes
    now_min = _time_to_minutes(now)

    if end_min <= 1440:
        return start_min <= now_min < end_min
    else:
        # Wraps past midnight
        return now_min >= start_min or now_min < (end_min % 1440)


def _check_interval(schedule: IntervalSchedule, now: time) -> bool:
    """Check if now falls within any of the evenly-spaced interval windows."""
    count = schedule.interval_count
    per_run = schedule.total_minutes / count
    spacing = 1440 / count
    now_min = _time_to_minutes(now)

    for i in range(count):
        start = (spacing * i) % 1440
        end = start + per_run
        if end <= 1440:
            if start <= now_min < end:
                return True
        else:
            if now_min >= start or now_min < (end % 1440):
                return True
    return False


def _check_dawn_dusk(schedule: DawnDuskSchedule, now: time) -> bool:
    """Check if now falls within dawn or dusk watering windows."""
    half = schedule.total_minutes / 2
    dawn = _parse_time(schedule.dawn_time)
    dusk = _parse_time(schedule.dusk_time)

    dawn_min = _time_to_minutes(dawn)
    dusk_min = _time_to_minutes(dusk)
    now_min = _time_to_minutes(now)

    for start_min in (dawn_min, dusk_min):
        end_min = start_min + half
        if end_min <= 1440:
            if start_min <= now_min < end_min:
                return True
        else:
            if now_min >= start_min or now_min < (end_min % 1440):
                return True
    return False


def _next_on_off(
    schedule: RelaySchedule, now: time
) -> tuple[str | None, str | None]:
    """Compute next ON and next OFF times for display."""
    windows = _get_windows(schedule)
    if not windows:
        return None, None

    now_min = _time_to_minutes(now)

    # Check if we're currently inside a window
    for start, end in windows:
        in_window = False
        if end <= 1440:
            in_window = start <= now_min < end
        else:
            in_window = now_min >= start or now_min < (end % 1440)

        if in_window:
            off_min = end % 1440
            # Find next window after this one
            next_windows = [(s, e) for s, e in windows if s != start]
            future = [s for s, _ in next_windows if s > now_min]
            wrap = [s for s, _ in next_windows if s <= now_min]
            next_on_min = future[0] if future else (wrap[0] if wrap else start)
            return _minutes_to_hhmm(next_on_min), _minutes_to_hhmm(off_min)

    # Not in any window — find the next one
    future = [(s, e) for s, e in windows if s > now_min]
    if future:
        s, e = future[0]
    else:
        s, e = windows[0]  # wraps to tomorrow

    return _minutes_to_hhmm(s), _minutes_to_hhmm(e % 1440)


def _get_windows(schedule: RelaySchedule) -> list[tuple[int, int]]:
    """Return list of (start_minutes, end_minutes) windows."""
    if isinstance(schedule, SingleSchedule):
        start = _time_to_minutes(_parse_time(schedule.start_time))
        return [(start, start + schedule.total_minutes)]

    elif isinstance(schedule, IntervalSchedule):
        count = schedule.interval_count
        per_run = schedule.total_minutes / count
        spacing = 1440 / count
        return [
            (int(spacing * i) % 1440, int(spacing * i + per_run))
            for i in range(count)
        ]

    elif isinstance(schedule, DawnDuskSchedule):
        half = schedule.total_minutes / 2
        dawn = _time_to_minutes(_parse_time(schedule.dawn_time))
        dusk = _time_to_minutes(_parse_time(schedule.dusk_time))
        return [(dawn, int(dawn + half)), (dusk, int(dusk + half))]

    return []


def _minutes_to_hhmm(minutes: int) -> str:
    """Convert minutes since midnight to HH:MM string."""
    minutes = minutes % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
