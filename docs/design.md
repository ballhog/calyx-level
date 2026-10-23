# Calyx-Level: how it works

Implements the decisions in *Corallite ATO - architecture 2026-10-22*. Numbers marked **(proposed)** are starting
values to test on the bench, not settled.

## 1. Pieces

```
            sump / tank                                              RO station  (~20 ft)
 ┌────────────────────────────────┐   Cat6, PoE switch   ┌──────────────────────────────────────┐
 │ SENSOR NODE                    │ ──── lease (UDP) ──► │ PUMP NODE                            │
 │ ESP32-POE-ISO + Uno carrier    │ ◄─── status ──────── │ ESP32-POE-ISO + Uno carrier          │
 │  · normal level A (optical)    │                      │  · MOSFET (pump B) / stepper (pump A) │
 │  · normal level B (optical)    │                      │  · own limits: run, off, daily cap   │
 │  · RO reservoir low            │                      │  · senses the high float (read only) │
 │  · leak (optional)             │                      │  · logs ml and run time              │
 └────────────────────────────────┘                      └──────────────────────────────────────┘
        high-level float ═════════ 2-core shielded pair, ~20 ft ═════════► relay coil in series
                                                                            with pump power
```

| Role | Where | Job |
|---|---|---|
| `sensor` | at the sump | Decides when water is needed. Grants leases. Refuses when its own sensors look wrong. |
| `pump` | at the RO station | Runs the pump only on a fresh lease and only inside its own limits. |
| `single` | one box | Short runs: the pump node reads the level jacks itself. Same firmware, same limits, no network in the loop. |

Same board, same carrier, same pin map and one firmware image for every role. The role is set once and stored in
NVS ([provisioning.md](provisioning.md)).

## 2. The lease

The sensor node never says "on". While the level is low and its sensors are healthy, it sends

> "pump node P may run for up to **N** ms; this is grant number **seq** of my boot **boot_id**"

every **1 s** with **N = 3,000 ms** (proposed). The pump node runs while `now < expiry` of the newest valid lease.

- Messages stop for any reason (cable, switch reboot, broadcast storm, sensor node crash or reboot) → the lease
  expires within N → pump off.
- Level reaches normal → the sensor node stops granting and also sends an explicit `revoke`, so the pump stops at
  once instead of after N.
- A lease is valid only if: it's addressed to this pump node's id; its HMAC checks (shared key set at provisioning);
  `boot_id` matches the current sensor boot (a new boot_id is accepted only after a `hello`); and `seq` is higher than
  the last one seen. That blocks replays and stray packets from a bench unit on the same LAN.
- The pump node ignores leases longer than its own `lease_max_ms` (proposed 5,000) and clamps to it.

Transport: plain UDP unicast between the two nodes, port 4510 (proposed). No broker in the safety path; MQTT or
HTTP only for reporting. Losing a packet costs nothing, because the next one arrives in 1 s and N covers three.

## 3. Pump node limits

These hold whatever the sensor node asks for. Each is a config value with a hard ceiling compiled in.

| Limit | Proposed default | Why |
|---|---|---|
| Max run per cycle | 120 s (~160 ml at 81 ml/min) | A stuck level sensor can't run the pump long |
| Min off time between runs | 60 s | Lets the level settle; stops short-cycling |
| Daily volume cap | 2 × 7-day mean daily volume, floor set at commissioning | Bounds a slow failure (stuck-low sensor) |
| Lease max | 5 s | A bad or forged lease can't buy long run time |
| Pump on with high float open | never | The relay already cuts power; firmware also drops the gate and alarms |

Hitting any cap → pump off, latched fault, alarm. Clearing a latched fault needs a person: the button on the pump
node, or a signed-in action on Coeno that sends an `ack` (Coeno sends the ack; it still can't make the pump run).

Stuck-on sizing, kept from the doser doc: 1 h at 81 ml/min ≈ 4.9 L, 150 ml/min ≈ 9 L, 1,800 ml/min ≈ 108 L.
The slow pump is part of the safety design.

## 4. Sensor node: when it refuses to grant

The sensor node grants only when the level is low **and** everything below is fine:

- **Two normal-level sensors agree.** Both "low" → grant. Disagree for more than 30 s (proposed) → unhealthy, no
  grant, alarm. One sensor alone is allowed only by an explicit config flag (bench, or single-sensor installs).
- **Plausible timing.** Low with no recovery after the pump has run its per-cycle max → stuck sensor or empty
  reservoir; stop granting and alarm.
- **Reservoir not empty.** RO-low sensor tripped → no grant, alarm.
- **Inputs within range.** An open or shorted sensor cable (reads permanently one way with a known-bad pattern, or
  flickers faster than water can move) → unhealthy.
- **Leak sensor dry** (if fitted).
- **Debounce.** A level change counts after it's held for 2 s (proposed), so surface ripple doesn't toggle grants.

## 5. What happens when things fail

| Failure | Result |
|---|---|
| Cable pulled / switch down / sensor node dead | Lease expires in ≤ 3 s → pump off. Pump node alarms "no heartbeat". |
| Pump node dead | Pump unpowered (MOSFET gate pulled down). Sensor node alarms "no pump status". |
| One level sensor fails | Sensors disagree → no grants → alarm. Tank level drops slowly; nothing overfills. |
| Both level sensors stuck "low" | Per-cycle max, then the daily cap, then the high float. |
| High float fails open-circuit | Relay drops → pump can't run (fails safe). Alarm. |
| Firmware bug in both nodes | High float still cuts pump power in hardware. |
| Coeno / Xanthe / Pi down | Nothing changes. ATO keeps working; logs back-fill later. |
| Power loss / reboot | Pump node boots with gate low and no lease; sensor node sends `hello`, then grants again. |
| OTA update | Pump and single-box nodes install only while idle with no lease held ([provisioning.md](provisioning.md)). |

## 6. Inputs (Apex-style sensors)

Level sensors plug in on 3.5 mm TRS cables, the same plug the Apex FMM sensors use. On the bench the jack board is
the SparkFun MyoWare 2.0 Arduino shield (6 jacks, A0–A5). Before trusting it:

- **Verify the TRS pinout on both sides with a meter.** The MyoWare shield is believed to be tip = signal,
  ring = power, sleeve = ground. Check which conductor an Apex FMM port powers and which one switches. If they
  differ, use panel TRS jacks wired to match instead of the shield.
- **Sensor supply.** Set the shield jumper to 3.3 V if the optical sensors work at 3.3 V. If they need 5 V and drive
  a 5 V output, the carrier's divider takes it down (see [schematic.md](schematic.md)).
- **Pull-ups.** Float switches and open-collector optical outputs need them; the carrier fits 10 kΩ to 3.3 V on
  every level input (the ESP32 input-only pins have no internal pull-ups).

## 7. Reporting

- Each node serves `GET /status` (JSON: role, node id, firmware build, inputs, lease state, today's ml and run time,
  latched faults) and `GET /log` (recent runs).
- Run log: ring buffer in LittleFS, back-filled to Xanthe after outages. Pump node logs ml per run (pump B:
  run seconds × calibrated ml/s; pump A: steps ÷ steps/ml).
- **ml/day is the evaporation record.** Xanthe trends it; a sudden change is worth an alert (leak, skimmer, heat).
- Alerts reach Telegram through Coeno/Xanthe. Reporting is read-only: no endpoint can start the pump.

## 8. Pump options

- **B (now):** the current brushed Kamoer (81 ml/min) on a logic-level MOSFET. Run minutes stay comparable with the
  Hydros ATO history.
- **A (later):** a KPHM100-class stepper head on a TMC2209 stepstick, same model as the salt-swap pump, so one
  spare covers both. Driver VIO on 3.3 V (see [schematic.md](schematic.md)).

## 9. Open

1. Pick the normal-level and high-level sensors (optical / capacitive / float), and measure the Apex TRS pinout.
2. Lease N, grant interval, debounce and disagreement windows: confirm on the bench.
3. Measure the real daily evaporation to set the daily-cap floor.
4. Reporting path: Coeno polls `/status`, or nodes publish MQTT to the Pi's broker (reporting only, never control).
5. Pump B now, A later?
