ZMK_TARGET ?= dongle-nice
ZMK_DOCKER_IMAGE ?= zmkfirmware/zmk-build-arm:stable
ZMK_BUILD_JOBS ?= 7
ZMK_TERM_COLUMNS ?= $(shell tput cols 2>/dev/null || echo 80)
ZMK_TERM_LINES ?= $(shell tput lines 2>/dev/null || echo 24)
BATTERY_TUI_ARGS ?=
BATTERY_CLI_BIN ?= $(HOME)/.local/bin

.PHONY: help
help:
	@echo "Local ZMK build targets:"
	@echo "  make zmk-list             List build.yaml targets and aliases"
	@echo "  make zmk-setup            Create/update local west workspace"
	@echo "  make zmk-dongle           Build nice_nano dongle firmware"
	@echo "  make zmk-left             Build left half firmware"
	@echo "  make zmk-right            Build right half firmware"
	@echo "  make zmk-reset-nice       Build nice_nano settings_reset firmware"
	@echo "  make zmk-all              Build every target from build.yaml"
	@echo "  make zmk-pristine         Rebuild ZMK_TARGET from scratch, default: dongle-nice"
	@echo "  make zmk-update           Run west update"
	@echo "  make zmk-clean            Remove local build outputs"
	@echo "  make zmk-docker-dongle    Build nice_nano dongle in the GitHub Actions ZMK image"
	@echo "  make zmk-docker-all       Build every target with ZMK_BUILD_JOBS=$(ZMK_BUILD_JOBS)"
	@echo "  make battery-tui          Show both half-battery levels over BLE"
	@echo "  make battery-read         Print both half-battery levels once"
	@echo "  make install-battery-cli  Install the unified chbat command"

.PHONY: zmk-list
zmk-list:
	@./scripts/zmk-build list

.PHONY: zmk-setup
zmk-setup:
	@./scripts/zmk-build setup

.PHONY: zmk-update
zmk-update:
	@./scripts/zmk-build update

.PHONY: zmk-dongle
zmk-dongle:
	@./scripts/zmk-build build dongle-nice

.PHONY: zmk-left
zmk-left:
	@./scripts/zmk-build build left

.PHONY: zmk-right
zmk-right:
	@./scripts/zmk-build build right

.PHONY: zmk-reset-nice
zmk-reset-nice:
	@./scripts/zmk-build build reset-nice

.PHONY: zmk-all
zmk-all:
	@./scripts/zmk-build build --all --jobs $(ZMK_BUILD_JOBS)

.PHONY: zmk-pristine
zmk-pristine:
	@./scripts/zmk-build build --pristine $(ZMK_TARGET)

.PHONY: zmk-clean
zmk-clean:
	@./scripts/zmk-build clean

.PHONY: zmk-distclean
zmk-distclean:
	@./scripts/zmk-build clean --dist

.PHONY: zmk-docker-dongle
zmk-docker-dongle:
	@docker run --rm -t \
		--user "$$(id -u):$$(id -g)" \
		-e HOME=/tmp \
		-e ZMK_USE_SYSTEM_WEST=1 \
		-e ZMK_SKIP_PIP_PACKAGES=1 \
		-e COLUMNS=$(ZMK_TERM_COLUMNS) \
		-e LINES=$(ZMK_TERM_LINES) \
		-v "$$(pwd)":/work \
		-w /work \
		$(ZMK_DOCKER_IMAGE) \
		bash -lc './scripts/zmk-build build --system-west dongle-nice'

.PHONY: zmk-docker-all
zmk-docker-all:
	@docker run --rm -t \
		--user "$$(id -u):$$(id -g)" \
		-e HOME=/tmp \
		-e ZMK_USE_SYSTEM_WEST=1 \
		-e ZMK_SKIP_PIP_PACKAGES=1 \
		-e ZMK_BUILD_JOBS=$(ZMK_BUILD_JOBS) \
		-e COLUMNS=$(ZMK_TERM_COLUMNS) \
		-e LINES=$(ZMK_TERM_LINES) \
		-v "$$(pwd)":/work \
		-w /work \
		$(ZMK_DOCKER_IMAGE) \
		bash -lc './scripts/zmk-build build --system-west --all --jobs $(ZMK_BUILD_JOBS)'

.PHONY: battery-tui
battery-tui:
	@uv run tools/battery_tui.py --tui $(BATTERY_TUI_ARGS)

.PHONY: battery-read
battery-read:
	@uv run tools/battery_tui.py --short $(BATTERY_TUI_ARGS)

.PHONY: install-battery-cli
install-battery-cli:
	@CHBAT_BIN_DIR="$(BATTERY_CLI_BIN)" ./scripts/install-chbat
