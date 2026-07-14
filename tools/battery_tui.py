#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "bleak>=2.1,<4",
# ]
# ///

"""Show both Charybdis split-peripheral battery levels in a terminal UI."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import curses
import re
import sys
import time
from dataclasses import dataclass
from typing import Any

from bleak import BleakClient, BleakScanner


BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
USER_DESCRIPTION_UUID = "00002901-0000-1000-8000-00805f9b34fb"
PERIPHERAL_LABEL_RE = re.compile(r"^Peripheral\s+(\d+)$", re.IGNORECASE)

PAIR_TITLE = 1
PAIR_ACCENT = 2
PAIR_MUTED = 3
PAIR_GOOD = 4
PAIR_WARN = 5
PAIR_BAD = 6


def init_theme() -> None:
    """Initialize a gruvbox-inspired palette with an eight-color fallback."""
    if not curses.has_colors():
        return

    curses.start_color()
    with contextlib.suppress(curses.error):
        curses.use_default_colors()

    if curses.COLORS >= 256:
        # gruvbox: aqua, orange, gray, green, yellow, red
        colors = (108, 208, 245, 142, 214, 167)
    else:
        colors = (
            curses.COLOR_CYAN,
            curses.COLOR_MAGENTA,
            curses.COLOR_WHITE,
            curses.COLOR_GREEN,
            curses.COLOR_YELLOW,
            curses.COLOR_RED,
        )

    for pair, foreground in zip(range(PAIR_TITLE, PAIR_BAD + 1), colors):
        with contextlib.suppress(curses.error):
            curses.init_pair(pair, foreground, -1)


def themed(pair: int, attributes: int = 0) -> int:
    if not curses.has_colors():
        return attributes
    return curses.color_pair(pair) | attributes


def battery_style(value: int | None) -> int:
    if value is None or value < 20:
        return themed(PAIR_BAD)
    if value < 50:
        return themed(PAIR_WARN)
    return themed(PAIR_GOOD)


@dataclass
class BatteryReading:
    characteristic: Any
    label: str
    peripheral_index: int | None
    value: int | None = None
    updated_at: float | None = None


class BatteryMonitor:
    def __init__(
        self,
        *,
        name: str,
        address: str | None,
        labels: list[str],
        scan_timeout: float,
        poll_interval: float,
    ) -> None:
        self.name = name
        self.address = address
        self.labels = labels
        self.scan_timeout = scan_timeout
        self.poll_interval = poll_interval
        self.device_name = ""
        self.device_address = ""
        self.status = "Starting Bluetooth monitor..."
        self.connected = False
        self.readings: list[BatteryReading] = []
        self.last_error = ""
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def reconnect(self) -> None:
        self.status = "Reconnect requested..."
        self._wake.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                device = await self._find_device()
                if device is None:
                    await self._wait_or_wake(3)
                    continue
                await self._monitor_device(device)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # BLE backends expose platform-specific errors.
                self.connected = False
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.status = "Bluetooth error; retrying..."
                await self._wait_or_wake(3)

    async def _find_device(self) -> Any | None:
        target = self.address or self.name
        self.connected = False

        connected_device = await self._find_connected_macos_device()
        if connected_device is not None:
            return connected_device

        self.status = f"Scanning for {target!r}..."
        discovered = await BleakScanner.discover(
            timeout=self.scan_timeout,
            return_adv=True,
        )

        candidates: list[tuple[int, Any, str]] = []
        for device, advertisement in discovered.values():
            advertised_name = advertisement.local_name or device.name or "Unknown"
            if self.address:
                matches = device.address.casefold() == self.address.casefold()
            else:
                matches = self.name.casefold() in advertised_name.casefold()
            if matches:
                candidates.append((advertisement.rssi, device, advertised_name))

        if not candidates:
            self.status = f"No BLE device matching {target!r}; scanning again..."
            return None

        _, device, advertised_name = max(candidates, key=lambda item: item[0])
        self.device_name = advertised_name
        self.device_address = device.address
        return device

    async def _find_connected_macos_device(self) -> Any | None:
        """Return a matching peripheral already connected by macOS.

        A BLE peripheral normally stops advertising after it connects. A regular
        Bleak scan therefore cannot see a keyboard that macOS is already using as
        a HID device. CoreBluetooth can retrieve that existing system connection
        by service UUID without requiring another advertisement.
        """
        if sys.platform != "darwin":
            return None

        self.status = "Checking Bluetooth devices already connected to macOS..."

        # Bleak does not expose CoreBluetooth's retrieval API publicly. Build the
        # same BLEDevice details tuple used by Bleak's macOS scanner so the rest of
        # the connection and GATT code can remain backend-independent.
        from CoreBluetooth import CBUUID
        from Foundation import NSArray
        from bleak.backends.corebluetooth.CentralManagerDelegate import (
            CentralManagerDelegate,
        )
        from bleak.backends.device import BLEDevice

        manager = CentralManagerDelegate()
        await manager.wait_until_ready()
        services = (
            NSArray.alloc()
            .initWithArray_([CBUUID.UUIDWithString_(BATTERY_SERVICE_UUID)])
        )
        peripherals = manager.central_manager.retrieveConnectedPeripheralsWithServices_(
            services
        )

        matches: list[tuple[Any, str, str]] = []
        for peripheral in peripherals:
            name = str(peripheral.name() or "")
            address = str(peripheral.identifier().UUIDString())
            if self.address:
                matches_device = address.casefold() == self.address.casefold()
            else:
                matches_device = self.name.casefold() in name.casefold()
            if matches_device:
                matches.append((peripheral, name, address))

        if not matches:
            return None

        peripheral, name, address = matches[0]
        self.device_name = name or self.name
        self.device_address = address
        return BLEDevice(address, name or None, (peripheral, manager))

    async def read_once(self) -> list[BatteryReading]:
        device = await self._find_device()
        if device is None:
            raise RuntimeError(self.status)

        self.status = f"Connecting to {self.device_name}..."
        async with BleakClient(device) as client:
            self.connected = True
            self.readings = await self._discover_readings(client)
            if not self.readings:
                raise RuntimeError(
                    "no Battery Level characteristics found; flash the updated dongle firmware"
                )
            for reading in self.readings:
                await self._read_one(client, reading)
            return self.readings

    async def _monitor_device(self, device: Any) -> None:
        self.status = f"Connecting to {self.device_name}..."

        def disconnected(_: BleakClient) -> None:
            self.connected = False
            self.status = "Disconnected; reconnecting..."
            self._wake.set()

        async with BleakClient(device, disconnected_callback=disconnected) as client:
            self.connected = True
            self.last_error = ""
            self.status = "Discovering battery characteristics..."
            self.readings = await self._discover_readings(client)
            if not self.readings:
                raise RuntimeError(
                    "no Battery Level characteristics found; flash the updated dongle firmware"
                )

            for reading in self.readings:
                await self._read_one(client, reading)
                if "notify" in reading.characteristic.properties:
                    await client.start_notify(
                        reading.characteristic,
                        self._notification_handler(reading),
                    )

            count = len(self.readings)
            self.status = f"Connected; monitoring {count} battery level(s)"
            self._wake.clear()

            while client.is_connected and not self._stop.is_set():
                woke = await self._wait_or_wake(self.poll_interval)
                if self._stop.is_set() or woke:
                    break
                for reading in self.readings:
                    await self._read_one(client, reading)

    async def _discover_readings(self, client: BleakClient) -> list[BatteryReading]:
        readings: list[BatteryReading] = []
        for service in client.services:
            for characteristic in service.characteristics:
                if characteristic.uuid.casefold() != BATTERY_LEVEL_UUID:
                    continue
                label = ""
                for descriptor in characteristic.descriptors:
                    if descriptor.uuid.casefold() != USER_DESCRIPTION_UUID:
                        continue
                    try:
                        raw_label = await client.read_gatt_descriptor(descriptor)
                        label = raw_label.decode("utf-8", errors="replace").rstrip("\0")
                    except Exception:
                        pass
                    break

                match = PERIPHERAL_LABEL_RE.match(label)
                peripheral_index = int(match.group(1)) if match else None
                readings.append(
                    BatteryReading(
                        characteristic=characteristic,
                        label=label or f"Battery {characteristic.handle}",
                        peripheral_index=peripheral_index,
                    )
                )

        auxiliary = [
            reading for reading in readings if reading.peripheral_index is not None
        ]
        if auxiliary:
            readings = auxiliary
        readings.sort(
            key=lambda reading: (
                reading.peripheral_index is None,
                reading.peripheral_index
                if reading.peripheral_index is not None
                else reading.characteristic.handle,
            )
        )

        for index, reading in enumerate(readings):
            if index < len(self.labels):
                reading.label = self.labels[index]
        return readings

    async def _read_one(self, client: BleakClient, reading: BatteryReading) -> None:
        data = await client.read_gatt_char(reading.characteristic)
        self._update_reading(reading, data)

    def _notification_handler(self, reading: BatteryReading):
        def handler(_: Any, data: bytearray) -> None:
            self._update_reading(reading, data)

        return handler

    @staticmethod
    def _update_reading(reading: BatteryReading, data: bytearray) -> None:
        if not data:
            return
        reading.value = min(max(int(data[0]), 0), 100)
        reading.updated_at = time.monotonic()

    async def _wait_or_wake(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=timeout)
        except TimeoutError:
            return False
        self._wake.clear()
        return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="chbat",
        description="Display both Charybdis half-battery levels over BLE.",
    )
    parser.add_argument(
        "--name",
        default="Charybdis",
        help="case-insensitive substring of the advertised BLE name (default: Charybdis)",
    )
    parser.add_argument(
        "--address",
        help="exact BLE address; on macOS this is a CoreBluetooth UUID",
    )
    parser.add_argument(
        "--labels",
        default="Left,Right",
        help="comma-separated labels in split pairing order (default: Left,Right)",
    )
    parser.add_argument("--scan-timeout", type=float, default=5.0)
    parser.add_argument("--poll-interval", type=float, default=30.0)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--tui",
        action="store_true",
        help="start the full-screen terminal UI (default)",
    )
    mode.add_argument(
        "--short",
        "--once",
        dest="short",
        action="store_true",
        help="read both battery levels once and print them without starting the TUI",
    )
    args = parser.parse_args()
    args.labels = [label.strip() for label in args.labels.split(",") if label.strip()]
    return args


def safe_addstr(screen: Any, y: int, x: int, text: str, style: int = 0) -> None:
    rows, columns = screen.getmaxyx()
    if y < 0 or y >= rows or x < 0 or x >= columns:
        return
    with contextlib.suppress(curses.error):
        screen.addnstr(y, x, text, max(columns - x - 1, 0), style)


def render(screen: Any, monitor: BatteryMonitor) -> None:
    screen.erase()
    rows, columns = screen.getmaxyx()
    title = "Charybdis Battery Monitor"
    safe_addstr(
        screen,
        1,
        max((columns - len(title)) // 2, 0),
        title,
        themed(PAIR_TITLE, curses.A_BOLD),
    )
    safe_addstr(screen, 3, 2, "Device: ", themed(PAIR_MUTED))
    safe_addstr(screen, 3, 10, monitor.device_name or "-", themed(PAIR_ACCENT))
    safe_addstr(screen, 4, 2, "State:  ", themed(PAIR_MUTED))
    if monitor.last_error:
        state_style = themed(PAIR_BAD)
    elif monitor.connected:
        state_style = themed(PAIR_GOOD)
    else:
        state_style = themed(PAIR_WARN)
    safe_addstr(screen, 4, 10, monitor.status, state_style)

    top = 7
    if not monitor.readings:
        safe_addstr(screen, top, 2, "Waiting for battery data...")
    else:
        bar_width = max(min(columns - 28, 48), 8)
        for index, reading in enumerate(monitor.readings):
            y = top + (index * 3)
            value_text = "--" if reading.value is None else f"{reading.value:3d}%"
            value = reading.value or 0
            filled = round(bar_width * value / 100)
            age = ""
            if reading.updated_at is not None:
                age = f"  updated {int(time.monotonic() - reading.updated_at)}s ago"
            charge_style = battery_style(reading.value)
            safe_addstr(
                screen,
                y,
                2,
                reading.label,
                themed(PAIR_ACCENT, curses.A_BOLD),
            )
            safe_addstr(screen, y + 1, 2, "[", themed(PAIR_MUTED))
            safe_addstr(screen, y + 1, 3, "#" * filled, charge_style)
            safe_addstr(
                screen,
                y + 1,
                3 + filled,
                "-" * (bar_width - filled),
                themed(PAIR_MUTED, curses.A_DIM),
            )
            safe_addstr(
                screen, y + 1, 3 + bar_width, "]", themed(PAIR_MUTED)
            )
            safe_addstr(
                screen,
                y + 1,
                5 + bar_width,
                value_text,
                charge_style | curses.A_BOLD,
            )
            safe_addstr(
                screen,
                y + 1,
                5 + bar_width + len(value_text),
                age,
                themed(PAIR_MUTED, curses.A_DIM),
            )

    footer = "q: quit   r: reconnect/rescan"
    safe_addstr(screen, rows - 2, 2, footer, themed(PAIR_MUTED, curses.A_DIM))
    if monitor.last_error:
        safe_addstr(screen, rows - 3, 2, monitor.last_error, themed(PAIR_BAD))
    screen.refresh()


async def run_ui(screen: Any, args: argparse.Namespace) -> None:
    with contextlib.suppress(curses.error):
        curses.curs_set(0)
    init_theme()
    screen.nodelay(True)
    screen.timeout(0)

    monitor = BatteryMonitor(
        name=args.name,
        address=args.address,
        labels=args.labels,
        scan_timeout=args.scan_timeout,
        poll_interval=args.poll_interval,
    )
    monitor_task = asyncio.create_task(monitor.run())
    try:
        while True:
            render(screen, monitor)
            key = screen.getch()
            if key in (ord("q"), ord("Q")):
                return
            if key in (ord("r"), ord("R")):
                monitor.reconnect()
            await asyncio.sleep(0.1)
    finally:
        monitor.stop()
        monitor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor_task


async def run_once(args: argparse.Namespace) -> None:
    monitor = BatteryMonitor(
        name=args.name,
        address=args.address,
        labels=args.labels,
        scan_timeout=args.scan_timeout,
        poll_interval=args.poll_interval,
    )
    readings = await monitor.read_once()
    print(f"{monitor.device_name} ({monitor.device_address})")
    for reading in readings:
        value = "unknown" if reading.value is None else f"{reading.value}%"
        print(f"{reading.label}: {value}")


def main() -> None:
    args = parse_args()
    if args.short:
        asyncio.run(run_once(args))
        return
    curses.wrapper(lambda screen: asyncio.run(run_ui(screen, args)))


if __name__ == "__main__":
    main()
