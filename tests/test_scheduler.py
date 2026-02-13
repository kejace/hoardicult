"""Tests for SchedulerService."""

from datetime import time
from unittest.mock import AsyncMock, patch

import pytest

from hoardicult.devices.relay_expander import RelayController
from hoardicult.models.relay import (
    DawnDuskSchedule,
    IntervalSchedule,
    SingleSchedule,
)
from hoardicult.services.scheduler import (
    SchedulerService,
    _check_dawn_dusk,
    _check_interval,
    _check_single,
    _should_be_on,
)

# --- Pure function tests ---


class TestCheckSingle:
    def test_within_window(self) -> None:
        s = SingleSchedule(mode="single", total_minutes=30, start_time="06:00")
        assert _check_single(s, time(6, 0)) is True
        assert _check_single(s, time(6, 15)) is True
        assert _check_single(s, time(6, 29)) is True

    def test_outside_window(self) -> None:
        s = SingleSchedule(mode="single", total_minutes=30, start_time="06:00")
        assert _check_single(s, time(5, 59)) is False
        assert _check_single(s, time(6, 30)) is False
        assert _check_single(s, time(12, 0)) is False

    def test_midnight_wrap(self) -> None:
        s = SingleSchedule(mode="single", total_minutes=60, start_time="23:30")
        assert _check_single(s, time(23, 30)) is True
        assert _check_single(s, time(23, 59)) is True
        assert _check_single(s, time(0, 0)) is True
        assert _check_single(s, time(0, 29)) is True
        assert _check_single(s, time(0, 30)) is False
        assert _check_single(s, time(23, 29)) is False


class TestCheckInterval:
    def test_six_intervals(self) -> None:
        s = IntervalSchedule(mode="interval", total_minutes=30, interval_count=6)
        # 6 runs of 5min each, every 4 hours (0:00, 4:00, 8:00, 12:00, 16:00, 20:00)
        assert _check_interval(s, time(0, 0)) is True
        assert _check_interval(s, time(0, 4)) is True
        assert _check_interval(s, time(0, 5)) is False
        assert _check_interval(s, time(4, 0)) is True
        assert _check_interval(s, time(4, 4)) is True
        assert _check_interval(s, time(4, 5)) is False

    def test_two_intervals(self) -> None:
        s = IntervalSchedule(mode="interval", total_minutes=60, interval_count=2)
        # 2 runs of 30min each, every 12 hours (0:00, 12:00)
        assert _check_interval(s, time(0, 0)) is True
        assert _check_interval(s, time(0, 29)) is True
        assert _check_interval(s, time(0, 30)) is False
        assert _check_interval(s, time(12, 0)) is True
        assert _check_interval(s, time(12, 29)) is True
        assert _check_interval(s, time(12, 30)) is False

    def test_between_intervals(self) -> None:
        s = IntervalSchedule(mode="interval", total_minutes=30, interval_count=6)
        assert _check_interval(s, time(2, 0)) is False
        assert _check_interval(s, time(6, 0)) is False


class TestCheckDawnDusk:
    def test_dawn_window(self) -> None:
        s = DawnDuskSchedule(
            mode="dawn_dusk", total_minutes=30, dawn_time="06:00", dusk_time="18:00"
        )
        # Each window is 15 min
        assert _check_dawn_dusk(s, time(6, 0)) is True
        assert _check_dawn_dusk(s, time(6, 14)) is True
        assert _check_dawn_dusk(s, time(6, 15)) is False

    def test_dusk_window(self) -> None:
        s = DawnDuskSchedule(
            mode="dawn_dusk", total_minutes=30, dawn_time="06:00", dusk_time="18:00"
        )
        assert _check_dawn_dusk(s, time(18, 0)) is True
        assert _check_dawn_dusk(s, time(18, 14)) is True
        assert _check_dawn_dusk(s, time(18, 15)) is False

    def test_outside_both(self) -> None:
        s = DawnDuskSchedule(
            mode="dawn_dusk", total_minutes=30, dawn_time="06:00", dusk_time="18:00"
        )
        assert _check_dawn_dusk(s, time(12, 0)) is False
        assert _check_dawn_dusk(s, time(0, 0)) is False
        assert _check_dawn_dusk(s, time(5, 59)) is False


class TestShouldBeOn:
    def test_dispatches_single(self) -> None:
        s = SingleSchedule(mode="single", total_minutes=30, start_time="06:00")
        assert _should_be_on(s, time(6, 15)) is True
        assert _should_be_on(s, time(7, 0)) is False

    def test_dispatches_interval(self) -> None:
        s = IntervalSchedule(mode="interval", total_minutes=30, interval_count=6)
        assert _should_be_on(s, time(0, 3)) is True
        assert _should_be_on(s, time(2, 0)) is False

    def test_dispatches_dawn_dusk(self) -> None:
        s = DawnDuskSchedule(
            mode="dawn_dusk", total_minutes=30, dawn_time="06:00", dusk_time="18:00"
        )
        assert _should_be_on(s, time(6, 5)) is True
        assert _should_be_on(s, time(12, 0)) is False


# --- SchedulerService tests ---


@pytest.fixture
def mock_controller() -> RelayController:
    mock = AsyncMock(spec=RelayController)
    mock.is_connected = True
    mock.relay_on = AsyncMock()
    mock.relay_off = AsyncMock()
    mock.relay_on_simulated = AsyncMock()
    mock.relay_off_simulated = AsyncMock()
    return mock


@pytest.fixture
def board_configs_with_schedule() -> list[dict]:
    return [
        {
            "board_addr": 1,
            "name": "Test Board",
            "relay_count": 4,
            "relay_expander_count": 1,
            "schedules": {
                "1": {"mode": "single", "total_minutes": 30, "start_time": "06:00"},
            },
        }
    ]


class TestSchedulerTick:
    @pytest.mark.asyncio
    async def test_tick_turns_on_when_in_window(
        self, mock_controller: AsyncMock, board_configs_with_schedule: list[dict]
    ) -> None:
        svc = SchedulerService(mock_controller, board_configs_with_schedule)

        with patch(
            "hoardicult.services.scheduler.datetime"
        ) as mock_dt:
            mock_dt.now.return_value.time.return_value = time(6, 15)
            await svc._tick()

        mock_controller.relay_on.assert_called_once_with(1, 1)
        assert (1, 1) in svc._scheduler_active

    @pytest.mark.asyncio
    async def test_tick_does_not_recommand(
        self, mock_controller: AsyncMock, board_configs_with_schedule: list[dict]
    ) -> None:
        svc = SchedulerService(mock_controller, board_configs_with_schedule)
        svc._scheduler_active.add((1, 1))

        with patch(
            "hoardicult.services.scheduler.datetime"
        ) as mock_dt:
            mock_dt.now.return_value.time.return_value = time(6, 15)
            await svc._tick()

        mock_controller.relay_on.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_turns_off_outside_window(
        self, mock_controller: AsyncMock, board_configs_with_schedule: list[dict]
    ) -> None:
        svc = SchedulerService(mock_controller, board_configs_with_schedule)
        svc._scheduler_active.add((1, 1))

        with patch(
            "hoardicult.services.scheduler.datetime"
        ) as mock_dt:
            mock_dt.now.return_value.time.return_value = time(7, 0)
            await svc._tick()

        mock_controller.relay_off.assert_called_once_with(1, 1)
        assert (1, 1) not in svc._scheduler_active

    @pytest.mark.asyncio
    async def test_tick_uses_simulated_when_disconnected(
        self, mock_controller: AsyncMock, board_configs_with_schedule: list[dict]
    ) -> None:
        mock_controller.is_connected = False
        svc = SchedulerService(mock_controller, board_configs_with_schedule)

        with patch(
            "hoardicult.services.scheduler.datetime"
        ) as mock_dt:
            mock_dt.now.return_value.time.return_value = time(6, 15)
            await svc._tick()

        mock_controller.relay_on_simulated.assert_called_once_with(1, 1)
        mock_controller.relay_on.assert_not_called()


class TestSchedulerGetInfo:
    def test_returns_none_for_unscheduled(
        self, mock_controller: AsyncMock, board_configs_with_schedule: list[dict]
    ) -> None:
        svc = SchedulerService(mock_controller, board_configs_with_schedule)
        assert svc.get_schedule_info(1, 2) is None

    def test_returns_info_for_scheduled(
        self, mock_controller: AsyncMock, board_configs_with_schedule: list[dict]
    ) -> None:
        svc = SchedulerService(mock_controller, board_configs_with_schedule)
        info = svc.get_schedule_info(1, 1)
        assert info is not None
        assert info.mode == "single"
        assert info.total_minutes == 30

    def test_shows_active_when_scheduler_controlling(
        self, mock_controller: AsyncMock, board_configs_with_schedule: list[dict]
    ) -> None:
        svc = SchedulerService(mock_controller, board_configs_with_schedule)
        svc._scheduler_active.add((1, 1))
        info = svc.get_schedule_info(1, 1)
        assert info is not None
        assert info.scheduled is True


class TestSchedulerStop:
    @pytest.mark.asyncio
    async def test_stop_turns_off_active_relays(
        self, mock_controller: AsyncMock, board_configs_with_schedule: list[dict]
    ) -> None:
        svc = SchedulerService(mock_controller, board_configs_with_schedule)
        svc._scheduler_active.add((1, 1))
        # Start the scheduler so _task is set, then stop it
        svc.start()
        await svc.stop()

        mock_controller.relay_off.assert_called_once_with(1, 1)
        assert len(svc._scheduler_active) == 0
