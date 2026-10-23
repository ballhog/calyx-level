# Calyx-Level parts list

Prices only where already seen; everything else is to price. "Per node" = sensor node or pump node; a `single`
box needs one node's worth plus both input and output parts.

## Common to every node

| Qty | Part | Notes |
|---|---|---|
| 1 | **Olimex ESP32-POE-ISO** (WROOM, not WROVER) | Isolated PoE: these nodes touch tank water and (pump) an external supply. WROOM keeps GPIO16 free. Never USB and PoE together on a non-ISO board; the ISO board is safe for that, but keep the habit. |
| 1 | Blank Arduino Uno R3 proto shield (with IOREF, SDA/SCL-by-AREF pins) | The carrier. Wired to the pin map in [schematic.md](schematic.md). |
| 1 set | Female stacking headers (8+6+10+8 R3 set, plus 2×3 ICSP) | Shields plug in on top. |
| 1 | CuteDigi **Twins Shield** (SKU SHD_TWIN_B4), $9.99 | Optional: two shields side by side. Check its two slots are wired in parallel and IOREF reaches both. |
| ~1 m | 2×5 ribbon or short wires, UEXT/EXT headers to carrier | Or solder the Olimex under the carrier on its EXT headers. |
| 1 | Enclosure + RJ45 panel feed-through | PoE in, nothing else needed on the sensor node. |
| 1 | 3 mm LED + 330 Ω | Status LED on D5. |
| 1 | Small piezo buzzer + NPN (2N3904) + 1 kΩ | Local alarm on D6 (optional). |

## Sensor node

| Qty | Part | Notes |
|---|---|---|
| 1 | SparkFun **MyoWare 2.0 Arduino Shield**, $10.50 | Six 3.5 mm TRS jacks on A0–A5. Verify its TRS pinout against an Apex FMM port first; fallback below. |
| 6 | 3.5 mm TRS panel jacks | Fallback if the MyoWare pinout doesn't match Apex sensors (or for the built enclosure). |
| 2 | Normal-level sensors (optical, Apex-style TRS) | Two, so the node can detect a disagreeing or stuck sensor. Type still open. |
| 1 | RO reservoir low sensor (float or optical) | Stops grants and alarms when the reservoir is empty. |
| 1 | Leak probe (optional) | Spare jack. |
| 6 | 10 kΩ pull-ups, 1 kΩ series, 100 nF to GND | One set per level input (RC filter + protection). |
| 6 | Divider pairs 10 kΩ / 20 kΩ (fit only if a sensor outputs 5 V) | 5 V → 3.3 V. |
| 6 | ESD diode (e.g. PESD5V0S1BL or a 6-ch TVS array) | Long sensor cables near water. |

## Pump node

| Qty | Part | Notes |
|---|---|---|
| 1 | Logic-level N-MOSFET, e.g. IRLZ44N or AO3400 board | Pump B (brushed Kamoer). Gate 100 Ω series, 10 kΩ pull-down. |
| 1 | Flyback diode SS34 / 1N5822 | Across the pump motor. |
| 1 | Relay, 12 or 24 V coil, contact ≥ 3 A (or SSR) + 1N4007 across the coil | The hardwired high-level cutoff. Coil driven through the float; contact in series with pump +V. |
| 1 | PC817 opto + 2.2 kΩ (24 V) or 1 kΩ (12 V) | Lets the ESP32 *read* the high float. Read only. |
| 1 | Inline fuse holder + fuse (1 A to start) | On pump +V. |
| 1 | Pump supply 12 or 24 V (to match the pump) | Separate from PoE. |
| 1 | High-level float switch, normally closed when water is below it | Opens on high water → relay drops → pump unpowered. |
| ~7 m | 2-core shielded twisted pair (~20 ft run) | High float to pump node. Shield grounded at the pump node end only. |
| 1 | Pump B: current brushed Kamoer (81 ml/min) | On hand. |
| — | Later, pump A: Kamoer KPHM100-STB10 ($38) + TMC2209 stepstick + stepstick carrier shield | Driver VIO from 3.3 V; 24 V for the motor. |

## Bench extras

| Qty | Part | Notes |
|---|---|---|
| 1 | Cup + float or a spare Apex optical sensor | To exercise the jacks. |
| 1 | 12 V bench supply + a small DC motor or LED as a stand-in pump | Test leases and caps without water. |
| 1 | Unmanaged PoE switch port | Pull its cable mid-run to prove the lease expiry. |
