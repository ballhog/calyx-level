# Calyx-Level provisioning

How a new node gets its identity, its partner, and its firmware updates from Coeno.

## 1. First flash (USB)

Built in VS Code + PlatformIO on the Windows desktop, same as Calyx-Sense. Board env `esp32-poe-iso`,
`min_spiffs.csv` partitions (two ~1.9 MB app slots, LittleFS for the run log). Unplug PoE for the first USB flash
out of habit, even though the ISO board tolerates both.

## 2. Identity and role (USB serial, once per node)

Set over the USB console and stored in NVS. Never settable over the network, and an OTA update never changes them.

| Key | Example | Meaning |
|---|---|---|
| `role` | `sensor` / `pump` / `single` | What this node does ([design.md](design.md) §1) |
| `node_id` | `calyx-level-sensor-1`, `calyx-level-pump-1` | Name in logs, Xanthe and lease messages |
| `peer_id` + `peer_ip` | `calyx-level-pump-1`, `10.0.0.x` | The partner node (not used in `single`) |
| `lease_key` | 32 random bytes, same on both nodes | HMAC key for leases; generated on the sensor node, typed into the pump node |
| `pump_type` | `brushed` / `stepper` | Pump node only |
| `ml_per_s` or `steps_per_ml` | from calibration | Pump node only |
| `daily_cap_floor_ml` | from commissioning | Pump node only |

Console commands (planned): `show`, `set <key> <value>`, `keygen`, `calibrate`, `ack`, `update`, `reboot`.

Give each node a **DHCP reservation** on the LAN so `peer_ip` stays put (Node Zero owns the network). Mixing a bench
unit onto the same LAN is safe: a lease with the wrong node id or key is ignored.

## 3. Firmware updates from Coeno (live in Coeno `b9fa573`)

Same pull OTA as the knob and Calyx-Sense:

- Manifest: `http://10.0.0.228:8000/firmware/calyx-level/latest.json` → `{build, version, url, sha256, size}`.
- Binary: `/firmware/calyx-level/calyx-level-<n>.bin`, served from Coeno's `firmware/calyx-level/`.
- One image for all roles.
- Check 1 min after the network comes up, every 6 h, or on `update` at the USB console. SHA-256 verified before the
  slot switch.
- Rollback: if the new build doesn't get the network up and pass its self-test (inputs read, lease path or level
  logic running) within 120 s, or crashes on boot 3 times, it boots the old slot.
- **Pump and single-box nodes install only when idle:** pump off, no lease held, no latched fault being worked.
  Otherwise the download waits for the next idle window. During the reboot the pump is off by design (gate pulled
  down, lease gone).
- Update order: the sensor node first, then the pump node, so a lease format change never reaches a pump node
  before its sender.
- Plain HTTP + hash, no signature (same as the knob and Calyx-Sense). Signing images is a later step for all three.

## 4. Publishing a build

From this repo, with Coeno checked out beside it as `../coeno` (or `COENO_REPO=...`):

```bash
./publish.sh          # builds, names it calyx-level-<commit count>.bin, copies into ../coeno/firmware/calyx-level/
cd ../coeno && git add firmware/calyx-level && git commit -m "calyx-level b<n>" && git push
```

The Pi serves it after its next `bash UPDATE.sh`. Prune older `.bin` files; only the highest build is served.
`publish.sh` will be copied from calyx-sense when the firmware exists.

## 5. Commissioning checklist

1. Both nodes flashed, roles and ids set, `lease_key` matches (`show` on each prints a key fingerprint, not the key).
2. Sensor node `/status`: all inputs plausible; both level sensors agree.
3. Lift the level sensors (or lower the water) → grants start → pump runs → level returns → explicit revoke.
4. Pull the Cat6 on either node mid-run → pump stops within 3 s, both nodes alarm.
5. Lift the high float by hand mid-run → relay drops, pump stops, pump node reports `high_float_open`.
6. Hold a level sensor "low" → per-cycle max trips, latched fault, `ack` needed.
7. Set `daily_cap_floor_ml` from a week of measured top-off volume.
8. Check `/firmware/calyx-level/latest.json` answers (404 until the first build is published; nodes treat that as
   "nothing to do").
