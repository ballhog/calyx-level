# Calyx-Level schematic and pin map

Text schematic for the bench build (Olimex ESP32-POE-ISO + blank Uno proto shield). A KiCad carrier board can
come later from the same pin map; the firmware's `pins.h` will mirror the table below so nothing else changes.

## 1. Pin map (frozen for v1)

Olimex ESP32-POE-ISO, **WROOM** module. The LAN8720 Ethernet takes GPIO12 (PHY power), 17 (clock), 18, 19, 21, 22,
23, 25, 26, 27. GPIO1/3 stay on the USB serial console. That leaves the pins below.

| Uno pin | ESP32 | Olimex header | Signal | Dir | Notes |
|---|---|---|---|---|---|
| A0 | GPIO36 | UEXT 4 | `LVL_A` normal level sensor A | in | Input-only, no internal pull-up → external 10 kΩ |
| A1 | GPIO39 | EXT | `LVL_B` normal level sensor B | in | Input-only. Check the board's power-sense jumper is open |
| A2 | GPIO35 | EXT | `RO_LOW` reservoir empty | in | Input-only. Check the battery-sense jumper is open |
| A3 | GPIO32 | EXT | `LEAK` leak probe (optional) | in | |
| A4 | GPIO33 | EXT | `SPARE_IN1` | in | **Not** I2C on this carrier (see note) |
| A5 | GPIO4 | UEXT 3 | `SPARE_IN2` | in | **Not** I2C on this carrier |
| D2 | GPIO16 | UEXT 5 | `PUMP_EN` MOSFET gate (pump B) / driver EN (pump A) | out | Quiet at boot on WROOM. 10 kΩ pull-down (pump B) |
| D3 | GPIO13 | UEXT 6 | `STEP` (pump A) | out | |
| D4 | GPIO14 | UEXT 9 | `DIR` (pump A) | out | Toggles at boot; harmless while the driver is disabled |
| D5 | GPIO15 | UEXT 7 | `STATUS_LED` | out | Strapping pin; an LED is fine |
| D6 | GPIO2 | UEXT 8 | `BUZZER` (via NPN) | out | Strapping pin; base pull-down keeps it low at boot |
| D7 | GPIO5 | UEXT 10 | `HIGH_FLOAT_SENSE` (opto, read only) | in | Strapping pin wants high at boot; the pull-up does that |
| — | GPIO34 | on board | `BUT1` ack / reservoir refilled | in | Olimex button, not routed to the carrier |
| D0/D1, D8–D13, SDA/SCL, ICSP | — | — | not connected | | No SPI or I2C shields in v1 |
| 3V3 + IOREF | 3.3 V | UEXT 1 | logic supply | | IOREF = 3.3 V so modern shields use 3.3 V logic |
| 5V | 5 V | EXT | shield 5 V | | From the Olimex 5 V rail (PoE) |
| GND | GND | UEXT 2 | | | |

**Note on A4/A5:** on a real Uno these are the same wires as SDA/SCL. Here they are plain inputs so the MyoWare
board's jacks 5 and 6 are usable. Don't plug an I2C shield into a Calyx-Level carrier.

The same map is used by every role. A sensor node leaves D2–D4 and D7 unfitted; a pump node may leave the level
jacks empty; a `single` box uses both.

## 2. Level input (×6, A0–A5)

```
                 3V3
                  │
                 10k   pull-up (omit if sensor drives a push-pull 3.3 V output)
                  │
 TRS tip  ──┬─────┴──── 1k ──┬──── GPIO (A0..A5)
 (signal)   │                │
          ESD/TVS          100n
            │                │
 TRS sleeve ┴──── GND ───────┴────
 TRS ring  ─────── sensor supply: MyoWare jumper 3V3 or 5V (verify pinout first!)

 5 V-output sensor instead: replace the 10k pull-up with a divider at the jack:
   tip ── 10k ──┬── (to 1k series) ;  node ── 20k ── GND   →  5 V → 3.33 V
```

Float switches and open-collector optical outputs read **low = switch closed**. Firmware sets polarity per input.

## 3. Pump node power stage (pump B, brushed Kamoer)

```
 PUMP SUPPLY +V (12/24 V to match pump)
   │
  FUSE 1A
   │
   ├──────────────────────────────────────────────┐
   │                                              │
   │      ~20 ft shielded pair to the tank        │
   │   ┌──────────────────────────────────┐       │
   └───┤ HIGH FLOAT (closed = water OK)   ├──┐    │
       └──────────────────────────────────┘  │    │
                                             │    │
            ┌────────────── RELAY COIL ──────┤    │
            │      1N4007 across coil        │    │
            │                                │    │
            │   PC817 LED + 2.2k (24V)/1k(12V)    │
            │   in parallel with the coil ───┘    │
            │   PC817 transistor: C → GPIO5 (10k pull-up to 3V3), E → GND
            │                                     │
          GND_PUMP                    RELAY CONTACT (NO, closes when coil powered)
                                                  │
                                              PUMP (+)
                                     SS34 flyback │  (cathode to +)
                                              PUMP (−)
                                                  │
                                            MOSFET drain  (IRLZ44N / AO3400)
                  GPIO16 ── 100Ω ── gate ─┤
                                10k gate → source
                                            MOSFET source
                                                  │
                                              GND_PUMP ═══ ESP32 GND (ISO board side)
```

The pump runs only when **both** are true: the relay is closed (float says water is below the high mark, and the
cable is intact) **and** the ESP32 holds the gate high. A cut float cable drops the relay. A dead ESP32 leaves the
gate pulled down. Neither path depends on the network.

Ground: on the ISO board the ESP32 side is isolated from the PoE side, so tying ESP32 GND to the pump supply ground
is fine. Do this only on the ISO board.

## 4. Pump node, later: pump A (stepper)

```
 TMC2209 stepstick (standalone, MS1/MS2 by jumper)
   VIO  ← 3V3          (so 3.3 V STEP/DIR/EN are proper logic levels)
   VM   ← relay contact output (same high-float relay as above), 24 V, 100 µF at the stepstick
   EN   ← GPIO16, plus 10k pull-up to VIO  → driver disabled at boot and when the ESP32 is dead (EN is active low)
   STEP ← GPIO13      DIR ← GPIO14
```
Firmware flips `PUMP_EN` polarity by config (`pump_type: brushed | stepper`).

## 5. Sensor node extras

- `STATUS_LED` GPIO15 → 330 Ω → LED → GND.
- `BUZZER` GPIO2 → 1 kΩ → 2N3904 base (10 kΩ base to GND); piezo between 5 V and the collector.

## 6. Bench checks before plugging in sensors

1. Continuity: Twins shield slot 1 ↔ slot 2 for every pin; IOREF reaches both slots.
2. MyoWare shield: which TRS conductor goes to A-pin, which to the power jumper, which to GND.
3. Apex FMM port with a sensor plugged in: which conductor carries supply, which switches, what voltage it swings.
4. With nothing plugged in, every level input reads high (pull-ups present).
5. Pump stage on the bench supply with a stand-in load: gate low at power-up, relay drops when the float wire is
   pulled, opto reports it on GPIO5.
