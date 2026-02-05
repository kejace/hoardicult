"""Tests for IOExpander class."""

from unittest.mock import MagicMock, patch

import pytest

from hoardicult.devices.ioexpander import (
    IOExpander,
    IOExpanderConnectionError,
)


class TestIOExpanderInit:
    """Test IOExpander initialization."""

    def test_default_settings(self) -> None:
        """IOExpander uses default settings from config."""
        io = IOExpander()
        assert io.port == "/dev/serial0"
        assert io.baudrate == 115200

    def test_custom_settings(self) -> None:
        """IOExpander accepts custom port and baudrate."""
        io = IOExpander(port="/dev/ttyACM0", baudrate=9600, timeout=2.0)
        assert io.port == "/dev/ttyACM0"
        assert io.baudrate == 9600
        assert io.timeout == 2.0

    def test_not_connected_initially(self) -> None:
        """IOExpander is not connected after init."""
        io = IOExpander()
        assert io.is_connected is False


class TestIOExpanderConnection:
    """Test IOExpander connection management."""

    @patch("hoardicult.devices.ioexpander.serial.Serial")
    def test_connect_opens_serial(self, mock_serial: MagicMock) -> None:
        """connect() opens serial port with correct parameters."""
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_serial.return_value = mock_instance

        io = IOExpander(port="/dev/test", baudrate=9600)
        io.connect()

        mock_serial.assert_called_once()
        call_kwargs = mock_serial.call_args.kwargs
        assert call_kwargs["port"] == "/dev/test"
        assert call_kwargs["baudrate"] == 9600
        assert io.is_connected is True

    @patch("hoardicult.devices.ioexpander.serial.Serial")
    def test_connect_raises_on_failure(self, mock_serial: MagicMock) -> None:
        """connect() raises IOExpanderConnectionError on serial failure."""
        import serial

        mock_serial.side_effect = serial.SerialException("Port not found")

        io = IOExpander()
        with pytest.raises(IOExpanderConnectionError, match="Failed to connect"):
            io.connect()

    @patch("hoardicult.devices.ioexpander.serial.Serial")
    def test_disconnect_closes_serial(self, mock_serial: MagicMock) -> None:
        """disconnect() closes the serial port."""
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_serial.return_value = mock_instance

        io = IOExpander()
        io.connect()
        io.disconnect()

        mock_instance.close.assert_called_once()
        assert io.is_connected is False

    @patch("hoardicult.devices.ioexpander.serial.Serial")
    def test_context_manager(self, mock_serial: MagicMock) -> None:
        """IOExpander works as context manager."""
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_serial.return_value = mock_instance

        with IOExpander() as io:
            assert io.is_connected is True

        mock_instance.close.assert_called_once()


class TestIOExpanderCommands:
    """Test IOExpander command sending."""

    @patch("hoardicult.devices.ioexpander.serial.Serial")
    def test_send_command_writes_and_reads(self, mock_serial: MagicMock) -> None:
        """send_command writes command and returns response."""
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_instance.readline.return_value = b"OK\n"
        mock_serial.return_value = mock_instance

        io = IOExpander()
        io.connect()
        response = io.send_command("test")

        mock_instance.write.assert_called_once_with(b"test")
        assert response == "OK"

    def test_send_command_raises_when_not_connected(self) -> None:
        """send_command raises when not connected."""
        io = IOExpander()
        with pytest.raises(IOExpanderConnectionError):
            io.send_command("test")


class TestIOExpanderAddressing:
    """Test 9-bit multi-drop addressing."""

    def test_address_board_validates_range(self) -> None:
        """_address_board validates board address range."""
        io = IOExpander()
        io._serial = MagicMock()
        io._serial.is_open = True

        with pytest.raises(ValueError, match="must be 0-255"):
            io._address_board(256)

        with pytest.raises(ValueError, match="must be 0-255"):
            io._address_board(-1)

    @patch("hoardicult.devices.ioexpander.serial.Serial")
    def test_address_board_caches_current_board(self, mock_serial: MagicMock) -> None:
        """_address_board caches the current board to avoid redundant addressing."""
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_serial.return_value = mock_instance

        io = IOExpander()
        io.connect()

        # First call should write the address
        io._address_board(5)
        assert io._current_board == 5

        # Second call to same address should not write
        write_count = mock_instance.write.call_count
        io._address_board(5)
        assert mock_instance.write.call_count == write_count  # No new writes

        # Different address should write
        io._address_board(10)
        assert io._current_board == 10
        assert mock_instance.write.call_count > write_count


class TestIOExpanderAsync:
    """Test async command interface."""

    @pytest.mark.asyncio
    @patch("hoardicult.devices.ioexpander.serial.Serial")
    async def test_send_command_to_board(self, mock_serial: MagicMock) -> None:
        """send_command_to_board addresses board and sends command."""
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_instance.readline.return_value = b"response\n"
        mock_serial.return_value = mock_instance

        io = IOExpander()
        io.connect()

        response = await io.send_command_to_board(1, "test_cmd")

        assert response == "response"
        # Should have written address byte and command
        assert mock_instance.write.call_count >= 2

    @pytest.mark.asyncio
    async def test_send_command_to_board_raises_when_not_connected(self) -> None:
        """send_command_to_board raises when not connected."""
        io = IOExpander()
        with pytest.raises(IOExpanderConnectionError):
            await io.send_command_to_board(1, "test")
