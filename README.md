# Hoardicult

Plant watering controller with IOExpander integration.

## Features

- FastAPI backend for monitoring and control
- IOExpander serial communication for sensors and actuators
- Web interface for watering schedules and sensor data

## Quick Start

```bash
# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env

# Run the server
uv run uvicorn hoardicult.main:app --reload
```

## Hardware

This project uses [IOExpander](https://www.zevendevelopment.com/ioexpander.html) boards for sensor and actuator control via serial communication.
