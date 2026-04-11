# Debugging insights

## Клавиатура не реагирует на нажатия

### Случайное переключение на слой RESET
В кеймапе есть комбо `combo_reset_layer_left` (позиции 20+24) и `combo_reset_layer_right` (25+29), которые переключают на слой RESET. Слой RESET почти пустой — везде `&trans`, который на единственном активном слое ничего не делает. Выглядит как мёртвая клавиатура.

**Выход:** нажать `combo_normal` (позиции 7+8 — клавиши N7 и N8 в верхнем ряду правой половины). Комбо работает на любом слое и возвращает на BASE.

---

## Правая половина не работает после перепрошивки

### Диагностика через USB
Подключи правую половину к маку по USB и открой: **Option +  → Системный отчёт → USB**.

- Появился **USB-накопитель** (bootloader) — прошивка крашится при старте
- Появился **Unnamed Device, производитель ZMK Project** — прошивка работает, проблема только в BLE паринге с донглом
- Ничего не появилось — проблема с железом или кабелем (проверь что кабель передаёт данные, а не только питание)

Правая половина как периферийное устройство **не показывается как клавиатура** по USB — только через BLE → донгл. Это нормально.

### BLE паринг требует близости
После использования reset-файлов BLE-бонды стираются и паринг начинается с нуля. При первом включении после перепрошивки положи все три контроллера рядом (10–20 см). После успешного паринга работают на любом расстоянии в пределах комнаты.

Симптом: левая половина работает, правая нет — потому что донгл лежал ближе к левой половине.

### Порядок прошивки (критично)
1. Правая половина → `settings_reset` → `charybdis_right` → **выключить**
2. Левая половина → `settings_reset` → `charybdis_left` → **выключить**
3. Убедиться что **обе половины выключены**
4. Донгл → `settings_reset` → прошивка донгла
5. **Одновременно** включить обе половины

---

## Миграция на Zephyr 4.1 (ZMK main, декабрь 2025)

### Новые имена плат в build.yaml
| Старое | Новое |
|--------|-------|
| `nice_nano_v2` | `nice_nano//zmk` |
| `seeeduino_xiao_ble` | `xiao_ble//zmk` |

### PMW3610 драйвер (charybdis_3610.dtsi)
Zephyr 4.1 добавил встроенный драйвер с `compatible = "pixart,pmw3610"`, который требует `motion-gpios`. Чтобы использовать драйвер badjeff (с `irq-gpios`), нужен другой compatible string:

```dts
compatible = "pixart,pmw3610-alt";
```

### PMW3610 настройки переехали из Kconfig в devicetree
Старые Kconfig-символы (`PMW3610_SWAP_XY`, `PMW3610_INVERT_X/Y`, `PMW3610_REST*_*`) удалены. Теперь в `charybdis_3610.dtsi`:

```dts
trackball: trackball@0 {
    compatible = "pixart,pmw3610-alt";
    ...
    swap-xy;
    invert-x;
    invert-y;
};
```

Kconfig-символ тоже переименован: `CONFIG_PMW3610=y` → `CONFIG_PMW3610_ALT=y`

### prospector-zmk-module
- Ветка `main` — только для ZMK v0.3 (Zephyr 3.5)
- Ветка `feat/new-status-screens` — для ZMK main (Zephyr 4.1)

В `config/west.yml`:
```yaml
- name: prospector-zmk-module
  remote: carrefinho
  revision: feat/new-status-screens
```

---

## GitHub Actions — устаревшие версии (Node.js 20 → 24)

В `.github/workflows/draw_keymaps.yaml`:

| Старое | Новое |
|--------|-------|
| `actions/checkout@v4` | `actions/checkout@v6` |
| `stefanzweifel/git-auto-commit-action@v5` | `stefanzweifel/git-auto-commit-action@v7` |
