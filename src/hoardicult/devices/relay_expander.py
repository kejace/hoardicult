"""RelayExpander control for solenoid valves.

RelayExpander boards daisy-chain from IOExpander boards, providing up to 16 units
per IOExpander with 16 relays each (256 relays total per IOExpander board).

Commands use the 'e' prefix:
- e<n>o: Turn relay n ON (1-256)
- e<n>f: Turn relay n OFF
- es<hex>: Set multiple relays via hex (0=on, 1=off)
- eg<n>: Get relay n state
- eb<n>: Configure RelayExpander count (1-16)

Reference: https://www.zevendevelopment.com/relayexpander.html
"""

import asyncio
from enum import Enum

from hoardicult.devices.ioexpander import IOExpander


class RelayState(str, Enum):
    """Relay state enumeration."""

    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


class RelayController:
    """Control relays via RelayExpander boards connected to IOExpander."""

    def __init__(self, ioexpander: IOExpander) -> None:
        """Initialize relay controller.

        Args:
            ioexpander: Connected IOExpander instance for communication
        """
        self._io = ioexpander
        # Track relay states: (board_addr, relay_num) -> state
        self._states: dict[tuple[int, int], RelayState] = {}
        # Track which relays are simulated (not sent to hardware)
        self._simulated: set[tuple[int, int]] = set()

    @property
    def is_connected(self) -> bool:
        """Check if IOExpander is connected."""
        return self._io.is_connected

    def is_simulated(self, board_addr: int, relay_num: int) -> bool:
        """Check if relay state is simulated (not sent to hardware)."""
        return (board_addr, relay_num) in self._simulated

    async def relay_on(self, board_addr: int, relay_num: int) -> None:
        """Turn on a relay (activate solenoid valve).

        Args:
            board_addr: IOExpander board address (1-255)
            relay_num: Relay number (1-256)
        """
        self._validate_relay_num(relay_num)
        await self._io.send_command_to_board(
            board_addr, f"e{relay_num}o", expect_response=False
        )
        self._states[(board_addr, relay_num)] = RelayState.ON
        self._simulated.discard((board_addr, relay_num))

    async def relay_off(self, board_addr: int, relay_num: int) -> None:
        """Turn off a relay (deactivate solenoid valve).

        Args:
            board_addr: IOExpander board address (1-255)
            relay_num: Relay number (1-256)
        """
        self._validate_relay_num(relay_num)
        await self._io.send_command_to_board(
            board_addr, f"e{relay_num}f", expect_response=False
        )
        self._states[(board_addr, relay_num)] = RelayState.OFF
        self._simulated.discard((board_addr, relay_num))

    def relay_on_simulated(self, board_addr: int, relay_num: int) -> None:
        """Simulate turning on a relay (state only, no hardware command).

        Args:
            board_addr: IOExpander board address (1-255)
            relay_num: Relay number (1-256)
        """
        self._validate_relay_num(relay_num)
        self._states[(board_addr, relay_num)] = RelayState.ON
        self._simulated.add((board_addr, relay_num))

    def relay_off_simulated(self, board_addr: int, relay_num: int) -> None:
        """Simulate turning off a relay (state only, no hardware command).

        Args:
            board_addr: IOExpander board address (1-255)
            relay_num: Relay number (1-256)
        """
        self._validate_relay_num(relay_num)
        self._states[(board_addr, relay_num)] = RelayState.OFF
        self._simulated.add((board_addr, relay_num))

    def get_relay_state(self, board_addr: int, relay_num: int) -> RelayState:
        """Get cached state of a relay.

        Note: This returns the last known state from commands sent through
        this controller. Hardware state may differ if controlled externally.

        Args:
            board_addr: IOExpander board address (1-255)
            relay_num: Relay number (1-256)

        Returns:
            Last known relay state, or UNKNOWN if never set
        """
        return self._states.get((board_addr, relay_num), RelayState.UNKNOWN)

    async def close_all_on_board(self, board_addr: int, relay_count: int = 256) -> None:
        """Close all relays on a board (emergency shutoff).

        Args:
            board_addr: IOExpander board address (1-255)
            relay_count: Number of relays to close (default: all 256)
        """
        # Use hex command to set all bits to 1 (off)
        # Each hex digit represents 4 relays, 256 relays = 64 hex digits
        hex_digits = (relay_count + 3) // 4  # Round up
        hex_string = "f" * hex_digits
        await self._io.send_command_to_board(
            board_addr, f"es{hex_string}", expect_response=False
        )

        # Update cached states and clear simulated flags
        for key in list(self._states.keys()):
            if key[0] == board_addr:
                self._states[key] = RelayState.OFF
                self._simulated.discard(key)

    def close_all_on_board_simulated(
        self, board_addr: int, relay_count: int = 256
    ) -> None:
        """Simulate closing all relays on a board (state only, no hardware).

        Args:
            board_addr: IOExpander board address (1-255)
            relay_count: Number of relays to close (default: all 256)
        """
        for relay_num in range(1, relay_count + 1):
            key = (board_addr, relay_num)
            self._states[key] = RelayState.OFF
            self._simulated.add(key)

    async def set_relay_expander_count(self, board_addr: int, count: int) -> None:
        """Configure the number of RelayExpander boards connected.

        Must be called during initialization to tell the IOExpander how many
        RelayExpander boards are daisy-chained.

        Args:
            board_addr: IOExpander board address (1-255)
            count: Number of RelayExpander boards (1-16)
        """
        if not 1 <= count <= 16:
            raise ValueError(f"RelayExpander count must be 1-16, got {count}")
        await self._io.send_command_to_board(
            board_addr, f"eb{count}", expect_response=False
        )

    async def get_relay_state_from_hardware(
        self, board_addr: int, relay_num: int
    ) -> RelayState:
        """Query actual relay state from hardware.

        Args:
            board_addr: IOExpander board address (1-255)
            relay_num: Relay number (1-256)

        Returns:
            Current relay state from hardware
        """
        self._validate_relay_num(relay_num)
        response = await self._io.send_command_to_board(board_addr, f"eg{relay_num}")
        if response == "1":
            state = RelayState.ON
        elif response == "0":
            state = RelayState.OFF
        else:
            state = RelayState.UNKNOWN
        self._states[(board_addr, relay_num)] = state
        return state

    async def run_demo(
        self,
        board_addr: int,
        relay_count: int,
        delay_ms: int = 100,
    ) -> None:
        """Run running-light demo pattern across relays.

        Creates a "wave" effect by turning on each relay sequentially while
        turning off the previous one.

        Args:
            board_addr: IOExpander board address (1-255)
            relay_count: Number of relays to cycle through
            delay_ms: Delay between steps in milliseconds
        """
        delay_sec = delay_ms / 1000.0
        prev_relay: int | None = None

        for relay_num in range(1, relay_count + 1):
            if prev_relay:
                await self.relay_off(board_addr, prev_relay)
            await self.relay_on(board_addr, relay_num)
            await asyncio.sleep(delay_sec)
            prev_relay = relay_num

        # Turn off final relay
        if prev_relay:
            await self.relay_off(board_addr, prev_relay)

    async def run_demo_simulated(
        self,
        board_addr: int,
        relay_count: int,
        delay_ms: int = 100,
    ) -> None:
        """Run simulated running-light demo (state only, no hardware).

        Creates a "wave" effect by updating relay states sequentially
        without sending commands to hardware.

        Args:
            board_addr: IOExpander board address (1-255)
            relay_count: Number of relays to cycle through
            delay_ms: Delay between steps in milliseconds
        """
        delay_sec = delay_ms / 1000.0
        prev_relay: int | None = None

        for relay_num in range(1, relay_count + 1):
            self.relay_on_simulated(board_addr, relay_num)
            await asyncio.sleep(delay_sec)
            if prev_relay:
                self.relay_off_simulated(board_addr, prev_relay)
            prev_relay = relay_num

        # Turn off final relay
        if prev_relay:
            self.relay_off_simulated(board_addr, prev_relay)

    def _validate_relay_num(self, relay_num: int) -> None:
        """Validate relay number is in valid range."""
        if not 1 <= relay_num <= 256:
            raise ValueError(f"Relay number must be 1-256, got {relay_num}")
