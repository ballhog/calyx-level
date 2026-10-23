# Calyx-Level

Wired, fail-safe auto top-off (ATO) for a reef system. Part of the Corallite **Calyx** family
(wired connected devices: Calyx-Outlet, Calyx-Sense, Calyx-Level).

Built for Joe's own tank first. Each step should be useful on its own; it becomes a product only if it proves itself.

## In one paragraph

A **sensor node** at the sump reads the water level and the RO reservoir, and while water is needed it keeps
handing a short **run permission (lease)** over Ethernet to a **pump node** at the RO station. The pump node runs
the pump only while it holds a fresh lease and stays inside its own limits (run time, off time, daily volume).
Anything that breaks (cable, switch, either node, firmware) makes the lease run out and the pump stop. A
**hardwired high-level float** cuts pump power in series, with no firmware or network in the path. Both nodes are
Olimex ESP32-POE-ISO boards on a blank Arduino Uno proto shield, so off-the-shelf Uno shields plug straight in.

## Docs

| Doc | What's in it |
|---|---|
| [docs/design.md](docs/design.md) | How it works: roles, lease protocol, limits, sensor health, failure table, reporting |
| [docs/parts.md](docs/parts.md) | Parts list (bench build and per node), with what's already on hand |
| [docs/schematic.md](docs/schematic.md) | Wiring, pin map (Uno names ↔ ESP32 GPIO), input/output circuits, power |
| [docs/provisioning.md](docs/provisioning.md) | First flash, node role and id, Coeno OTA, publishing builds |

## Status (2026-10-23)

Design only. No firmware yet. Coeno already serves `/firmware/calyx-level/latest.json` (Coeno `b9fa573`).

## Related

- Corallite project docs: *Corallite ATO - architecture 2026-10-22* (the decisions this repo implements),
  *Corallite doser - E4 controller 2026-10-22*, *Salt swap doser - parked 2026-10-20*.
- [ballhog/calyx-sense](https://github.com/ballhog/calyx-sense): same board family, same OTA client.
- Coeno `firmware/calyx-level/` and `coeno/api/routes/firmware.py`: the OTA server.

## Rules that don't bend

1. Safety lives on the boxes. Xanthe and Coeno read and alert; they never switch the pump.
2. The high-level cutoff is hardware in series with pump power. It is never a shield input or a firmware decision.
3. No network message ever means "run". Only a fresh lease does, and silence means stop.
