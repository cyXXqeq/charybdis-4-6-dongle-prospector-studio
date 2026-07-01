# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a ZMK firmware configuration for the Charybdis 4x6 split ergonomic keyboard with trackball. The keyboard uses a three-controller dongle setup (left half, right half, dongle) and supports ZMK STUDIO for live keymap editing.

**Build system**: Firmware can be compiled via GitHub Actions using the ZMK build pipeline, or locally through the Make targets backed by `scripts/zmk-build`.

## Building Firmware

Push changes to trigger the GitHub Actions workflow (`.github/workflows/build.yml`), which uses `zmkfirmware/zmk/.github/workflows/build-user-config.yml`. Build artifacts are downloadable from the Actions tab.

Local build helpers:
- `make zmk-list` — list targets parsed from `build.yaml`
- `make zmk-dongle` — build the nice_nano dongle firmware
- `make zmk-docker-dongle` — build the nice_nano dongle firmware in the same `zmkfirmware/zmk-build-arm:stable` image used by GitHub Actions
- `make zmk-all` — build every target from `build.yaml`

Local build outputs are written to `artifacts/firmware/`. The local west workspace and build cache live under `.zmk-local/`.

The `build.yaml` defines the matrix of firmware targets:
- `charybdis_dongle` + `nice_nano_v2` — dongle firmware for Nice Nano v2
- `charybdis_dongle prospector_adapter` + `seeeduino_xiao_ble` — dongle for Prospector controller
- `charybdis_dongle` + `seeeduino_xiao_ble` — dongle for XIAO BLE
- `charybdis_left` / `charybdis_right` + `nice_nano_v2` — left/right halves
- `settings_reset` targets for both controller types

All dongle builds include `-DCONFIG_ZMK_STUDIO=y` and the `studio-rpc-usb-uart` snippet for ZMK STUDIO support.

## Repository Structure

```
config/
  charybdis.keymap        # Main keymap definition (layers, combos, bindings)
  charybdis.conf          # Shared config (BT TX power, experimental BLE conn)
  charybdis_left.conf     # Left-half specific config
  charybdis_right.conf    # Right-half specific config
  west.yml                # ZMK dependency manifest (zmk, pmw3610 driver, prospector module)
  charybdis.json          # Physical layout for ZMK STUDIO
  charybdis-layouts.dtsi  # Layout definitions

boards/shields/charybdis/
  charybdis.dtsi              # Base shield: matrix transform, physical layout (4x6 + thumb clusters)
  charybdis_left.overlay      # Left half GPIO matrix wiring
  charybdis_right.overlay     # Right half GPIO matrix wiring + trackball (includes charybdis_3610.dtsi)
  charybdis_dongle.overlay    # Dongle: uses mock kscan, enables trackball_listener
  charybdis_3610.dtsi         # PMW3610 trackball sensor SPI config (CPI, pins)
  split_input_common.dtsi     # Shared trackball input processing (layers, scroll, snipe)
  Kconfig.defconfig           # ZMK split role config (dongle = central)
  Kconfig.shield              # Shield selection Kconfig

keymap-drawer/
  config.yaml             # keymap-drawer rendering config
  charybdis.yaml          # Generated keymap YAML (auto-committed by CI)
  charybdis.svg           # Generated keymap SVG (auto-committed by CI)
```

## Key Architecture Concepts

### Split Keyboard Architecture
The dongle is the central controller (`ZMK_SPLIT_ROLE_CENTRAL`). Both halves are peripherals. Keymap and combos live only on the central (dongle). When modifying the keymap, only the dongle needs to be reflashed.

### Trackball Input Pipeline
The PMW3610 trackball is on the right half, forwarded over BLE split to the dongle via `zmk,input-split`. The `split_input_common.dtsi` configures three behaviors:
- **Normal movement** (`DEF` layer): raw pointer movement
- **Snipe** (`NUM` layer): scaled down 1/3 for precision
- **Scroll** (`FN` layer): Y-inverted, scaled 1/48, mapped to scroll wheel

### Layer Numbering (defined in `split_input_common.dtsi`)
```
DEF=0, MOUSE=1, SYM=2, NUM=3, FN=4, GENSHIN=5
```

### ZMK STUDIO
The studio unlock combo is keys 1+5 (first and fifth key pressed simultaneously). To disable studio locking, add `CONFIG_ZMK_STUDIO_LOCKING=n` to a `.conf` file.

### Auto Mouse Layer
The auto mouse layer (`&auto_mouse_layer MOUSE 400`) is currently **disabled** in `split_input_common.dtsi`. Re-enable by uncommenting that line in the `move` block.

## External Dependencies (`config/west.yml`)
- `zmkfirmware/zmk` — main ZMK framework (main branch)
- `badjeff/zmk-pmw3610-driver` — PMW3610 trackball sensor driver
- `carrefinho/prospector-zmk-module` — Prospector controller support

## Modifying Trackball Sensitivity
Edit `cpi` value in `boards/shields/charybdis/charybdis_3610.dtsi`. After changing CPI, both the dongle **and** the right half (which hosts the trackball) must be reflashed.

## Keymap Diagrams
After each push, CI auto-generates SVG keymap diagrams via `keymap-drawer` and amends the commit. The `draw_keymaps.yaml` workflow uses `keymap-drawer/config.yaml` for styling and `keymap-drawer/charybdis.yaml` as intermediate parse output.
