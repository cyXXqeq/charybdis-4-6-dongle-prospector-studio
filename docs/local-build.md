# Local firmware build

Локальная сборка сделана вокруг того же `build.yaml`, который читает GitHub Actions. Скрипт берет target из матрицы, создает отдельный west workspace в `.zmk-local/workspace`, передает `config/` как `ZMK_CONFIG`, а корень этой репы подключает как ZMK module через `ZMK_EXTRA_MODULES`.

Это важно для этой репы: `zephyr/module.yml` объявляет локальный `board_root`, поэтому shields из `boards/shields/charybdis/` должны подключаться как extra module.

## Команды

Показать все target'ы и короткие alias'ы:

```sh
make zmk-list
```

Первичная native-настройка west workspace:

```sh
make zmk-setup
```

Собрать твой nice_nano dongle:

```sh
make zmk-dongle
```

UF2 появится в:

```text
artifacts/firmware/charybdis_dongle-nice_nano-zmk.uf2
```

Для полной пересборки одного target'а:

```sh
make zmk-pristine
```

По умолчанию `zmk-pristine` пересобирает `dongle-nice`. Для другого target'а:

```sh
make zmk-pristine ZMK_TARGET=left
```

## Docker-вариант как в GitHub Actions

GitHub Actions собирает прошивку в container image `zmkfirmware/zmk-build-arm:stable`. Чтобы локально использовать тот же image:

```sh
make zmk-docker-dongle
```

Первый запуск скачает Docker image и west modules, поэтому он будет долгим. Последующие сборки переиспользуют `.zmk-local/workspace` и `.zmk-local/build`.

Собрать все targets из `build.yaml`, как полный GitHub Actions matrix:

```sh
make zmk-docker-all
```

По умолчанию полная сборка запускает 7 targets параллельно. Изменить число параллельных jobs можно так:

```sh
ZMK_BUILD_JOBS=4 make zmk-docker-all
```

Все build-команды показывают компактный прогресс в терминале. Полный west/ninja output каждого target'а пишется в `.zmk-local/logs/`. Если нужен обычный текстовый вывод без live-перерисовки:

```sh
ZMK_PROGRESS=0 make zmk-docker-all
```

## Native requirements

Для native-сборки нужны обычные зависимости Zephyr/ZMK:

- Python 3
- CMake
- Ninja
- Zephyr SDK или совместимый ARM toolchain

`make zmk-setup` сам создает `.zmk-local/.venv` и ставит туда `west`, затем делает:

```sh
west init -l .zmk-local/workspace/config
west update --fetch-opt=--filter=tree:0
west zephyr-export
west packages pip --install
```

Если менялся `config/west.yml` или нужно синхронизировать локальный workspace с зафиксированными ревизиями:

```sh
make zmk-update
```

Основные внешние зависимости в `config/west.yml` закреплены на точных commit SHA, чтобы GitHub Actions и локальная сборка не получали разный код из плавающих веток. Обновлять эти SHA следует осознанно: сначала собрать `make zmk-all`, затем прошивать затронутые контроллеры одним комплектом артефактов.

## Useful targets

```sh
make zmk-dongle      # charybdis_dongle + nice_nano//zmk
make zmk-left        # charybdis_left + nice_nano//zmk
make zmk-right       # charybdis_right + nice_nano//zmk
make zmk-reset-nice  # settings_reset + nice_nano//zmk
make zmk-all         # every build.yaml target, parallel by ZMK_BUILD_JOBS
make zmk-clean       # remove build outputs and copied UF2 files
make zmk-distclean   # also remove west workspace and downloaded modules
```

Для обычного изменения keymap чаще всего нужен только:

```sh
make zmk-dongle
```
