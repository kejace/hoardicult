#!/usr/bin/env python3
"""Program IOExpander board addresses one at a time.

Connect each board individually to the serial bus, then run this script.
It reads boards.json and programs each board's address in order,
prompting you to swap boards between each step.
"""

import json
import sys
import termios
import time

import serial

BOARDS_CONFIG = "boards.json"
SERIAL_PORT = "/dev/serial0"
BAUDRATE = 115200
CMSPAR = 0x40000000


def open_serial():
    ser = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2.0,
    )
    # Activate 9-bit multi-drop mode
    if sys.platform == "linux":
        ser.write(bytes([0]))
        ser.flush()
        time.sleep(0.1)
        ser.reset_input_buffer()
    return ser


def set_mark_parity(ser):
    """MARK parity (9th bit = 1) for address byte."""
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(ser)
    cflag |= termios.PARENB | CMSPAR | termios.PARODD
    termios.tcsetattr(ser, termios.TCSANOW,
                      [iflag, oflag, cflag, lflag, ispeed, ospeed, cc])


def set_space_parity(ser):
    """SPACE parity (9th bit = 0) for data bytes."""
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(ser)
    cflag |= termios.PARENB | CMSPAR
    cflag &= ~termios.PARODD
    termios.tcsetattr(ser, termios.TCSANOW,
                      [iflag, oflag, cflag, lflag, ispeed, ospeed, cc])


def address_board(ser, addr):
    """Send address byte with MARK parity, then switch to SPACE."""
    set_mark_parity(ser)
    ser.write(bytes([addr]))
    ser.flush()
    set_space_parity(ser)


def send_command(ser, command):
    """Address broadcast (0) then send command and read response."""
    ser.reset_input_buffer()
    address_board(ser, 0)  # broadcast to any board
    ser.write((command + "\r").encode())
    ser.flush()
    ser.readline()  # discard echo
    response = ser.readline()
    return response.decode().strip()


def set_address(ser, addr):
    """Program board address via #b<addr> command."""
    ser.reset_input_buffer()
    address_board(ser, 0)
    ser.write((f"#b{addr}\r").encode())
    ser.flush()
    time.sleep(0.5)
    # Verify by reading back
    return send_command(ser, "#b")


def main():
    with open(BOARDS_CONFIG) as f:
        data = json.load(f)

    boards = data.get("boards", [])
    if not boards:
        print("No boards found in config.")
        return

    print(f"Found {len(boards)} board(s) in {BOARDS_CONFIG}:")
    for b in boards:
        print(f"  Address {b['board_addr']}: {b.get('name', '(unnamed)')}")
    print()

    for i, board in enumerate(boards):
        addr = board["board_addr"]
        name = board.get("name", "(unnamed)")

        print(f"--- Board {i + 1}/{len(boards)} ---")
        print(f"Connect ONLY the board for: {name} (will be address {addr})")
        input("Press Enter when ready...")

        ser = open_serial()
        try:
            # Check current address
            current = send_command(ser, "#b")
            print(f"  Current address: {current}")

            # Program new address
            print(f"  Programming address to {addr}...")
            result = set_address(ser, addr)
            print(f"  Verified address: {result}")

            if result == str(addr):
                print(f"  OK - {name} is now address {addr}")
            else:
                print(f"  WARNING: expected {addr}, got {result}")
                if input("  Continue anyway? [y/N] ").lower() != "y":
                    return
        finally:
            ser.close()

        print()

    print("All boards programmed. Reconnect all boards to the bus.")
    print("Then restart the service: sudo systemctl restart hoardicult")


if __name__ == "__main__":
    main()
