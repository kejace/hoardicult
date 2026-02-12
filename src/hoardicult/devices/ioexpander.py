"""IOExpander serial communication with 9-bit multi-drop addressing.

IOExpander is a distributed sensor controller board from Zeven Development.
Communication: Serial at 115200 baud, 8N1.
Protocol: Single-character commands (e.g., 's6t5;sr' configures and reads a sensor).

9-bit multi-drop addressing allows up to 255 boards on a single serial bus.
Address selection uses MARK parity (9th bit = 1) for the address byte,
then SPACE parity (9th bit = 0) for command data.

Reference: https://www.zevendevelopment.com/ioexpander.html
"""

import asyncio
import sys
import termios

import serial

from hoardicult.core.config import settings

# Linux-specific "stick parity" flag for 9-bit addressing
CMSPAR = 0x40000000


class IOExpanderError(Exception):
    """Base exception for IOExpander errors."""


class IOExpanderConnectionError(IOExpanderError):
    """Failed to connect to IOExpander."""


class IOExpanderTimeoutError(IOExpanderError):
    """Command timed out."""


class IOExpander:
    """Interface for IOExpander board communication with 9-bit multi-drop addressing."""

    def __init__(
        self,
        port: str = settings.serial_port,
        baudrate: int = settings.serial_baudrate,
        timeout: float = 1.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None
        self._lock = asyncio.Lock()
        self._current_board: int | None = None

    @property
    def is_connected(self) -> bool:
        """Check if serial connection is active."""
        return self._serial is not None and self._serial.is_open

    def connect(self) -> None:
        """Open serial connection to IOExpander."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
        except serial.SerialException as e:
            raise IOExpanderConnectionError(f"Failed to connect: {e}") from e

        if sys.platform == "linux":
            # Send zero byte to activate 9-bit multi-drop mode
            self._serial.write(bytes([0]))
            self._serial.flush()

    def disconnect(self) -> None:
        """Close serial connection."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            self._serial = None
        self._current_board = None

    def _set_mark_parity(self) -> None:
        """Set MARK parity (9th bit = 1) for address mode.

        Only works on Linux with CMSPAR support.
        Uses same approach as reference ioexpander9bit.py.
        """
        if not self._serial:
            raise IOExpanderConnectionError("Not connected")
        if sys.platform != "linux":
            return  # Skip on non-Linux (for testing)

        # Match reference implementation: unpack all termios attrs
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(
            self._serial
        )
        cflag |= termios.PARENB | CMSPAR | termios.PARODD
        termios.tcsetattr(
            self._serial,
            termios.TCSANOW,
            [iflag, oflag, cflag, lflag, ispeed, ospeed, cc],
        )

    def _set_space_parity(self) -> None:
        """Set SPACE parity (9th bit = 0) for data mode.

        Only works on Linux with CMSPAR support.
        Uses same approach as reference ioexpander9bit.py.
        """
        if not self._serial:
            raise IOExpanderConnectionError("Not connected")
        if sys.platform != "linux":
            return  # Skip on non-Linux (for testing)

        # Match reference implementation: unpack all termios attrs
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(
            self._serial
        )
        cflag |= termios.PARENB | CMSPAR
        cflag &= ~termios.PARODD
        termios.tcsetattr(
            self._serial,
            termios.TCSANOW,
            [iflag, oflag, cflag, lflag, ispeed, ospeed, cc],
        )

    def _address_board(self, board_address: int) -> None:
        """Send board address with MARK parity (9th bit = 1).

        Args:
            board_address: Board address 1-255 (0 is broadcast)
        """
        if not 0 <= board_address <= 255:
            raise ValueError(f"Board address must be 0-255, got {board_address}")

        if self._current_board == board_address:
            return  # Already addressed

        if not self._serial:
            raise IOExpanderConnectionError("Not connected")

        self._set_mark_parity()
        self._serial.write(bytes([board_address]))
        self._serial.flush()
        self._set_space_parity()
        self._current_board = board_address

    def _send_command_sync(
        self,
        board_address: int,
        command: str,
        expect_response: bool = True,
    ) -> str | None:
        """Synchronous command send to specific board.

        Args:
            board_address: Target board address (1-255, or 0 for broadcast)
            command: Command string to send
            expect_response: Whether to wait for and return response

        Returns:
            Response string if expect_response is True, else None
        """
        if not self.is_connected:
            raise IOExpanderConnectionError("Not connected to IOExpander")

        self._address_board(board_address)
        self._serial.write((command + "\r").encode())  # type: ignore[union-attr]
        self._serial.flush()  # type: ignore[union-attr]

        if expect_response:
            # Response format: "echo\r\nresult\r\n>"
            self._serial.readline()  # discard echo  # type: ignore[union-attr]
            response = self._serial.readline()  # type: ignore[union-attr]
            return response.decode().strip()
        return None

    async def send_command_to_board(
        self,
        board_address: int,
        command: str,
        expect_response: bool = True,
    ) -> str | None:
        """Send command to specific board with proper 9-bit addressing.

        Thread-safe async interface that serializes access to the serial port.

        Args:
            board_address: Target board address (1-255, or 0 for broadcast)
            command: Command string to send
            expect_response: Whether to wait for and return response

        Returns:
            Response string if expect_response is True, else None
        """
        async with self._lock:
            return await asyncio.get_event_loop().run_in_executor(
                None,
                self._send_command_sync,
                board_address,
                command,
                expect_response,
            )

    # Legacy method for single-board setups
    def send_command(self, command: str) -> str:
        """Send command to IOExpander (legacy single-board interface)."""
        if not self._serial or not self._serial.is_open:
            raise IOExpanderConnectionError("Not connected to IOExpander")
        self._serial.write((command + "\r").encode())
        response = self._serial.readline()
        return response.decode().strip()

    def __enter__(self) -> "IOExpander":
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.disconnect()
