#!/usr/bin/env python3
"""Program IOExpander board addresses one at a time.

Connect each board individually to the serial bus, then run this script.
It reads boards.json and programs each board's address in order,
prompting you to swap boards between each step.

Power-cycle each board before connecting to ensure it starts in
normal (non-multi-drop) mode.
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
    time.sleep(0.1)
    ser.reset_input_buffer()
    return ser


def set_mark(ser):
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(ser)
    cflag |= termios.PARENB | CMSPAR | termios.PARODD
    termios.tcsetattr(
        ser, termios.TCSANOW,
        [iflag, oflag, cflag, lflag, ispeed, ospeed, cc],
    )


def set_space(ser):
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(ser)
    cflag |= termios.PARENB | CMSPAR
    cflag &= ~termios.PARODD
    termios.tcsetattr(
        ser, termios.TCSANOW,
        [iflag, oflag, cflag, lflag, ispeed, ospeed, cc],
    )


def read_response(ser, wait=0.5):
    """Read all available bytes after waiting, parse response."""
    time.sleep(wait)
    avail = ser.in_waiting
    if not avail:
        return None
    data = ser.read(avail)
    # Response format: "echo\r\nresult\r\n>"
    parts = data.decode(errors="replace").split("\r\n")
    # Result is the second part (after echo)
    if len(parts) >= 2:
        return parts[1].strip()
    return parts[0].strip()


def try_normal_mode(ser, command):
    """Send command in normal mode (no addressing)."""
    ser.reset_input_buffer()
    ser.write(f"{command}\r".encode())
    ser.flush()
    return read_response(ser)


def try_multidrop(ser, addr, command):
    """Send command to a specific address in multi-drop mode."""
    ser.reset_input_buffer()
    set_mark(ser)
    ser.write(bytes([addr]))
    ser.flush()
    set_space(ser)
    ser.write(f"{command}\r".encode())
    ser.flush()
    return read_response(ser)


def enter_multidrop(ser):
    """Activate 9-bit multi-drop mode by sending zero byte."""
    ser.write(bytes([0]))
    ser.flush()
    time.sleep(0.1)
    ser.reset_input_buffer()


def find_board(ser):
    """Try to communicate with connected board, return current address."""
    # Try normal mode first
    print("  Trying normal mode...")
    result = try_normal_mode(ser, "#b")
    if result:
        print(f"  Found board in normal mode, address: {result}")
        return int(result), "normal"

    # Enter multi-drop and scan
    print("  No response in normal mode, trying multi-drop...")
    enter_multidrop(ser)

    for addr in range(1, 256):
        ser.reset_input_buffer()
        result = try_multidrop(ser, addr, "#b")
        if result:
            print(f"  Found board at address {addr} (reports: {result})")
            return int(result), "multidrop"
        if addr <= 10 or addr % 50 == 0:
            pass  # scan silently

    return None, None


def program_address(ser, old_addr, new_addr, mode):
    """Program board to new address."""
    if mode == "normal":
        ser.reset_input_buffer()
        ser.write(f"#b{new_addr}\r".encode())
        ser.flush()
        time.sleep(0.5)
        return try_normal_mode(ser, "#b")
    else:
        ser.reset_input_buffer()
        try_multidrop(ser, old_addr, f"#b{new_addr}")
        time.sleep(0.5)
        # Verify at new address
        return try_multidrop(ser, new_addr, "#b")


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
        target_addr = board["board_addr"]
        name = board.get("name", "(unnamed)")

        print(f"--- Board {i + 1}/{len(boards)} ---")
        print(f"Connect ONLY the board for: {name}")
        print(f"  (will be programmed to address {target_addr})")
        input("Press Enter when ready...")

        ser = open_serial()
        try:
            current_addr, mode = find_board(ser)

            if current_addr is None:
                print("  ERROR: No board detected!")
                print("  Check wiring and power, then try again.")
                if input("  Retry? [Y/n] ").lower() == "n":
                    return
                continue

            if current_addr == target_addr:
                print(f"  Already at address {target_addr}, no change needed.")
            else:
                print(f"  Programming {current_addr} -> {target_addr}...")
                result = program_address(
                    ser, current_addr, target_addr, mode
                )
                if result == str(target_addr):
                    print(f"  OK - {name} is now address {target_addr}")
                else:
                    print(f"  WARNING: expected {target_addr}, got {result}")
                    if input("  Continue? [y/N] ").lower() != "y":
                        return
        finally:
            ser.close()

        print()

    print("All boards programmed! Reconnect all boards to the bus.")
    print("Then restart: sudo systemctl restart hoardicult")


if __name__ == "__main__":
    main()
