# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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
- `make battery-tui` — monitor both half-battery levels in a terminal UI over BLE
- `make battery-read` — print both half-battery levels once
- `make install-battery-cli` — install the unified `chbat` command into `~/.local/bin`

Local build outputs are written to `artifacts/firmware/`. The local west workspace and build cache live under `.zmk-local/`.

The `build.yaml` defines the matrix of firmware targets:
- `charybdis_dongle` + `nice_nano//zmk` — dongle firmware for Nice Nano
- `charybdis_dongle prospector_adapter` + `xiao_ble//zmk` — dongle for Prospector controller
- `charybdis_dongle` + `xiao_ble//zmk` — dongle for XIAO BLE
- `charybdis_left` / `charybdis_right` + `nice_nano//zmk` — left/right halves
- `settings_reset` targets for both controller types

All dongle builds include `-DCONFIG_ZMK_STUDIO=y` and the `studio-rpc-usb-uart` snippet for ZMK STUDIO support.

## Git Workflow

- Create a commit after every completed code fix before handing the work back to the user.
- Include documentation and repository-guidance updates in the commit when they are part of the requested change.
- Push commits only after the user explicitly approves the push. Approval applies to the current requested push, not to future changes.
- Before pushing, fetch the remote branch and account for CI-generated keymap commits that may have amended the remote tip.

### CI keymap redraw rewrites the pushed commit

- `.github/workflows/build.yml` runs on every push and pull request. After a successful firmware build, its `keymap_images` job calls `.github/workflows/draw_keymaps.yaml`.
- The keymap workflow regenerates `keymap-drawer/charybdis.yaml` and `keymap-drawer/charybdis.svg`. With its current default `amend_commit: true`, changed generated files are committed with `git commit --amend --no-edit` and pushed with `--force-with-lease`.
- Consequently, CI may replace the commit that was just pushed instead of adding a child commit. The commit message stays the same, but `origin/main` gets a new SHA and the local branch appears to have diverged. If the generated files are unchanged, no rewrite is needed and the SHA can remain unchanged.
- After every push, wait for the workflow to finish and run `git fetch origin` before starting or committing more work. Compare `HEAD` with `origin/main`; do not rely only on a previously observed clean status.
- If the only divergence is the CI-amended replacement and there is no unique local or uncommitted work, realign the local branch to `origin/main` before editing. Do not merge the stale pre-CI tip with the amended tip, because that creates a redundant merge between two versions of the same logical commit.
- If local work already exists, preserve it and inspect both histories before reconciling them. Never discard local changes merely to match the CI rewrite.
- Treat the generated YAML and SVG in the amended remote commit as authoritative output. Do not overwrite them by pushing again from the stale pre-CI commit.

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

scripts/
  zmk-build               # Local build orchestration
  install-chbat           # Safe, idempotent installer for the battery CLI

tools/
  battery_tui.py          # BLE battery reader and full-screen TUI
  chbat                   # Unified command wrapper; defaults to TUI

docs/
  battery-monitor.md      # Installation, usage, and troubleshooting for chbat
  local-build.md          # Local ZMK build setup and workflow

keymap-drawer/
  config.yaml             # keymap-drawer rendering config
  charybdis.yaml          # Generated keymap YAML (auto-committed by CI)
  charybdis.svg           # Generated keymap SVG (auto-committed by CI)
```

## Key Architecture Concepts

### Split Keyboard Architecture
The dongle is the central controller (`ZMK_SPLIT_ROLE_CENTRAL`). Both halves are peripherals. Keymap and combos live only on the central (dongle). When modifying only key bindings, only the dongle needs to be reflashed.

The matrix transform is also compiled into both peripheral firmwares. If the order of `RC(...)` entries in `boards/shields/charybdis/charybdis.dtsi` changes, flash the dongle, left half, and right half from the same build. Mixing old peripheral transforms with a new dongle remaps physical key positions, especially in the thumb clusters.

### Battery Monitoring
The dongle fetches and proxies both peripheral battery levels over BLE. macOS displays only one Battery Service value in System Settings, so use the repository CLI to inspect both:

- `chbat` or `chbat --tui` — full-screen gruvbox-inspired monitor
- `chbat --short` — one-shot text output
- `scripts/install-chbat` — install `chbat` into `${CHBAT_BIN_DIR:-$HOME/.local/bin}`

The host must be connected directly to the dongle over BLE. On macOS, the tool retrieves an already connected CoreBluetooth peripheral before falling back to advertisement scanning.

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
- `zmkfirmware/zmk` — main ZMK framework, pinned to a tested commit
- `badjeff/zmk-pmw3610-driver` — PMW3610 trackball sensor driver, pinned to a tested commit
- `carrefinho/prospector-zmk-module` — Prospector controller support, pinned to a tested commit from `feat/new-status-screens`

Keep these dependencies on exact commit SHAs for reproducible local and CI builds. When intentionally updating them, build all targets and document the tested revision set.

## Modifying Trackball Sensitivity
Edit the `cpi` value in `boards/shields/charybdis/charybdis_3610.dtsi`. This sensor node is compiled only into the right-half firmware, so only the right half needs to be reflashed for a CPI-only change. Changes to the input-processing pipeline in `split_input_common.dtsi` can affect both the right half and dongle; rebuild and flash each target that compiles the changed node.

The PMW3610 report-rate limiter lives in `config/charybdis_right.conf` and is likewise compiled only into the right half. A report-interval-only change requires flashing only the right half and does not require `settings_reset`.

## Keymap Diagrams
After each successful build, CI auto-generates SVG keymap diagrams via `keymap-drawer`. The `draw_keymaps.yaml` workflow uses `keymap-drawer/config.yaml` for styling and `keymap-drawer/charybdis.yaml` as intermediate parse output. See **CI keymap redraw rewrites the pushed commit** under **Git Workflow** for the required fetch and history-reconciliation procedure.
