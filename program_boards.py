#!/usr/bin/env python3
"""Program IOExpander board addresses one at a time.

Connect each board individually to the serial bus, then run this script.
It reads boards.json and programs each board's address in order,
prompting you to swap boards between each step.
"""

import json
import time

import serial

BOARDS_CONFIG = "boards.json"
SERIAL_PORT = "/dev/serial0"
BAUDRATE = 115200


def open_serial():
    ser = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2.0,
    )
    # Do NOT send zero byte — stay in normal mode so the board
    # responds to commands without 9-bit addressing
    time.sleep(0.1)
    ser.reset_input_buffer()
    return ser


def send_command(ser, command):
    """Send command in normal (non-multi-drop) mode."""
    ser.reset_input_buffer()
    ser.write((command + "\r").encode())
    ser.flush()
    ser.readline()  # discard echo
    response = ser.readline()
    return response.decode().strip()


def set_address(ser, addr):
    """Program board address via #b<addr> command."""
    ser.reset_input_buffer()
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
