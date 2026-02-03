"""Tests for RelayController class."""

from unittest.mock import AsyncMock

import pytest

from hoardicult.devices.relay_expander import RelayController, RelayState


@pytest.fixture
def mock_ioexpander() -> AsyncMock:
    """Create mock IOExpander."""
    mock = AsyncMock()
    mock.send_command_to_board = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def controller(mock_ioexpander: AsyncMock) -> RelayController:
    """Create RelayController with mock IOExpander."""
    return RelayController(mock_ioexpander)


class TestRelayController:
    """Test RelayController operations."""

    @pytest.mark.asyncio
    async def test_relay_on_sends_correct_command(
        self, controller: RelayController, mock_ioexpander: AsyncMock
    ) -> None:
        """relay_on sends 'e<n>o' command to correct board."""
        await controller.relay_on(board_addr=1, relay_num=5)

        mock_ioexpander.send_command_to_board.assert_called_once_with(
            1, "e5o", expect_response=False
        )

    @pytest.mark.asyncio
    async def test_relay_off_sends_correct_command(
        self, controller: RelayController, mock_ioexpander: AsyncMock
    ) -> None:
        """relay_off sends 'e<n>f' command to correct board."""
        await controller.relay_off(board_addr=2, relay_num=10)

        mock_ioexpander.send_command_to_board.assert_called_once_with(
            2, "e10f", expect_response=False
        )

    @pytest.mark.asyncio
    async def test_relay_on_updates_state(
        self, controller: RelayController
    ) -> None:
        """relay_on updates cached state to ON."""
        await controller.relay_on(1, 5)

        state = controller.get_relay_state(1, 5)
        assert state == RelayState.ON

    @pytest.mark.asyncio
    async def test_relay_off_updates_state(
        self, controller: RelayController
    ) -> None:
        """relay_off updates cached state to OFF."""
        await controller.relay_off(1, 5)

        state = controller.get_relay_state(1, 5)
        assert state == RelayState.OFF

    def test_get_relay_state_returns_unknown_for_unset(
        self, controller: RelayController
    ) -> None:
        """get_relay_state returns UNKNOWN for relays never controlled."""
        state = controller.get_relay_state(1, 99)
        assert state == RelayState.UNKNOWN

    @pytest.mark.asyncio
    async def test_relay_on_validates_relay_number(
        self, controller: RelayController
    ) -> None:
        """relay_on validates relay number range."""
        with pytest.raises(ValueError, match="must be 1-256"):
            await controller.relay_on(1, 0)

        with pytest.raises(ValueError, match="must be 1-256"):
            await controller.relay_on(1, 257)

    @pytest.mark.asyncio
    async def test_relay_off_validates_relay_number(
        self, controller: RelayController
    ) -> None:
        """relay_off validates relay number range."""
        with pytest.raises(ValueError, match="must be 1-256"):
            await controller.relay_off(1, 0)

    @pytest.mark.asyncio
    async def test_close_all_on_board(
        self, controller: RelayController, mock_ioexpander: AsyncMock
    ) -> None:
        """close_all_on_board sends hex command to close all relays."""
        # Set some relays to ON first
        await controller.relay_on(1, 1)
        await controller.relay_on(1, 5)

        mock_ioexpander.send_command_to_board.reset_mock()

        await controller.close_all_on_board(board_addr=1, relay_count=16)

        # Should send hex command (4 hex digits for 16 relays)
        mock_ioexpander.send_command_to_board.assert_called_once()
        call_args = mock_ioexpander.send_command_to_board.call_args
        assert call_args[0][0] == 1  # board_addr
        assert call_args[0][1].startswith("es")  # hex set command
        assert call_args[1]["expect_response"] is False

        # States should be updated to OFF
        assert controller.get_relay_state(1, 1) == RelayState.OFF
        assert controller.get_relay_state(1, 5) == RelayState.OFF

    @pytest.mark.asyncio
    async def test_set_relay_expander_count(
        self, controller: RelayController, mock_ioexpander: AsyncMock
    ) -> None:
        """set_relay_expander_count sends 'eb<n>' command."""
        await controller.set_relay_expander_count(board_addr=1, count=4)

        mock_ioexpander.send_command_to_board.assert_called_once_with(
            1, "eb4", expect_response=False
        )

    @pytest.mark.asyncio
    async def test_set_relay_expander_count_validates_range(
        self, controller: RelayController
    ) -> None:
        """set_relay_expander_count validates count range."""
        with pytest.raises(ValueError, match="must be 1-16"):
            await controller.set_relay_expander_count(1, 0)

        with pytest.raises(ValueError, match="must be 1-16"):
            await controller.set_relay_expander_count(1, 17)

    @pytest.mark.asyncio
    async def test_get_relay_state_from_hardware(
        self, controller: RelayController, mock_ioexpander: AsyncMock
    ) -> None:
        """get_relay_state_from_hardware queries and caches state."""
        mock_ioexpander.send_command_to_board.return_value = "1"

        state = await controller.get_relay_state_from_hardware(1, 5)

        assert state == RelayState.ON
        assert controller.get_relay_state(1, 5) == RelayState.ON

        mock_ioexpander.send_command_to_board.assert_called_once_with(1, "eg5")

    @pytest.mark.asyncio
    async def test_get_relay_state_from_hardware_off(
        self, controller: RelayController, mock_ioexpander: AsyncMock
    ) -> None:
        """get_relay_state_from_hardware correctly parses OFF state."""
        mock_ioexpander.send_command_to_board.return_value = "0"

        state = await controller.get_relay_state_from_hardware(1, 5)

        assert state == RelayState.OFF


class TestRelayControllerMultiBoard:
    """Test RelayController with multiple boards."""

    @pytest.mark.asyncio
    async def test_states_isolated_per_board(
        self, controller: RelayController
    ) -> None:
        """Relay states are tracked separately per board."""
        await controller.relay_on(1, 5)
        await controller.relay_off(2, 5)

        assert controller.get_relay_state(1, 5) == RelayState.ON
        assert controller.get_relay_state(2, 5) == RelayState.OFF

    @pytest.mark.asyncio
    async def test_close_all_only_affects_specified_board(
        self, controller: RelayController
    ) -> None:
        """close_all_on_board only affects the specified board."""
        await controller.relay_on(1, 5)
        await controller.relay_on(2, 5)

        await controller.close_all_on_board(1, 16)

        assert controller.get_relay_state(1, 5) == RelayState.OFF
        assert controller.get_relay_state(2, 5) == RelayState.ON
