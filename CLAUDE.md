# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hoardicult is a plant watering controller system with:
- **FastAPI backend** for API and web interface
- **IOExpander + RelayExpander** for controlling 32+ solenoid valves via 9-bit multi-drop serial
- **SQLAlchemy** for data persistence (watering schedules, sensor readings, etc.)

## Commands

```bash
# Install dependencies (requires uv: curl -LsSf https://astral.sh/uv/install.sh | sh)
uv sync

# Run development server
uv run uvicorn hoardicult.main:app --reload

# Run all tests
uv run pytest

# Run single test file
uv run pytest tests/test_relay.py -v

# Lint code
uv run ruff check .

# Auto-fix lint issues
uv run ruff check --fix .

# Type checking
uv run mypy src/
```

## Architecture

```
src/hoardicult/
├── main.py              # FastAPI app with lifespan handler
├── api/
│   └── boards.py        # /boards/{addr}/relays/{num}/open|close endpoints
├── core/
│   └── config.py        # Settings from environment
├── devices/
│   ├── ioexpander.py    # 9-bit multi-drop serial communication
│   └── relay_expander.py # RelayController for valve control
├── models/
│   └── relay.py         # Pydantic models for API
└── services/
    └── config_loader.py # Board configuration loading
```

## Hardware Architecture

```
Raspberry Pi
    └── Serial (115200 baud, 9-bit addressing)
            ├── IOExpander Board 1 (address 1)
            │       └── RelayExpander chain (up to 256 relays)
            ├── IOExpander Board 2 (address 2)
            │       └── RelayExpander chain
            └── ... up to 255 boards
```

## 9-bit Multi-Drop Addressing

Multiple IOExpander boards share a single serial bus using 9-bit addressing:
- MARK parity (9th bit = 1) sends board address
- SPACE parity (9th bit = 0) sends command data
- Linux-specific (uses `CMSPAR` termios flag)
- Implementation: `devices/ioexpander.py`

## RelayExpander Commands

Commands use `e` prefix for relay control:
- `e<n>o` - Turn relay n ON (1-256)
- `e<n>f` - Turn relay n OFF
- `es<hex>` - Set multiple relays via hex
- `eb<n>` - Configure RelayExpander count (1-16)

## Configuration

Copy `.env.example` to `.env`:
- `SERIAL_PORT` - IOExpander device (e.g., `/dev/serial0`)
- `SERIAL_BAUDRATE` - Default 115200
- `BOARDS_CONFIG_PATH` - Path to `boards.json`

Copy `boards.example.json` to `boards.json` for board definitions.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/boards` | GET | List all boards |
| `/boards/{addr}/relays` | GET | List relays on board |
| `/boards/{addr}/relays/{num}/open` | POST | Open valve |
| `/boards/{addr}/relays/{num}/close` | POST | Close valve |
| `/boards/{addr}/close-all` | POST | Emergency close all on board |
| `/boards/close-all` | POST | Emergency close all system |
