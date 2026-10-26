#!/usr/bin/env python3
"""Build the Calyx-Level carrier board (placement, outline, nets) from the schematic netlist.

    kicad-cli sch export netlist --format kicadsexpr -o /tmp/cl.net \\
        hardware/calyx-level-carrier/calyx-level-carrier.kicad_sch
    python3 hardware/tools/gen_pcb.py /tmp/cl.net         # -> calyx-level-carrier.kicad_pcb (unrouted)
    python3 hardware/tools/route_pcb.py                    # Freerouting + pours + DRC

Like gen_schematic.py, this is a starting point: once the board has been edited by hand
in KiCad, the .kicad_pcb is the source and this script should not be re-run over it.

Coordinates are mm, KiCad page coordinates (y down). The Olimex ESP32-POE-ISO sits on top,
plugged into J1/J2 (nothing between them, so it can sit on low sockets), standing upright: RJ45 end on the bottom edge, antenna end overhanging the
top edge. Every connector (RJ45, level jacks, pump supply, float, pump, motor) comes out of the bottom long edge.
The 12/24 V pump side sits on the right, away from the level jacks.
Olimex (olx, oly) maps to carrier (olx + DX, oly + DY): same orientation, just shifted.
"""
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(HERE, '..', 'calyx-level-carrier')
PCB = os.path.join(PROJ, 'calyx-level-carrier.kicad_pcb')
SYSLIB = '/usr/share/kicad/footprints'
MM = pcbnew.FromMM

# ---- outline ---------------------------------------------------------------------------
X0, Y0, X1, Y1 = 100.0, 104.0, 287.0, 180.0     # 187 x 76 mm; all I/O on the bottom edge (y = Y1)
DX, DY = 17.85, -8.15                            # Olimex x 108..136; RJ45 end on y=180, antenna overhangs y<104
                                                 # (same Olimex position as the calyx-flow carrier)


def oly(olx_, oly_):
    return olx_ + DX, oly_ + DY


EXT1_X = oly(91.44, 0)[0]       # 109.29
EXT2_X = oly(116.84, 0)[0]      # 134.69
EXT_Y1 = oly(0, 123.22)[1]      # pin 1 y = 115.07, pin n at +2.54*(n-1)

JACK_X0, JACK_P = 145.0, 10.5   # level jacks J3..J8 (PJ-320D-4A, 10 mm wide), nose on the bottom edge
JACK_Y = Y1 - 8.35
MKDS_Y = Y1 - 4.6               # Phoenix MKDS: wire entry (+y side) on the bottom edge. CONFIRM before fab.

# ---- placement: ref -> (x, y, rot, side) -----------------------------------------------
P = {
    # Olimex sockets
    'J1': (EXT1_X, EXT_Y1, 0, 'F'), 'J2': (EXT2_X, EXT_Y1, 0, 'F'),
    # case mounting
    'H1': (104.0, 108.0, 0, 'F'), 'H2': (283.0, 108.0, 0, 'F'),
    'H3': (104.0, 176.0, 0, 'F'), 'H4': (283.0, 176.0, 0, 'F'),

    # status LED, sensor-supply jumper, buzzer: top band right of the Olimex
    'R70': (141.0, 113.0, 90, 'F'), 'D70': (141.0, 109.0, 90, 'F'),
    'BZ1': (151.0, 113.0, 0, 'F'), 'Q70': (166.5, 110.0, 0, 'F'), 'R71': (166.5, 114.5, 0, 'F'),
    'R72': (170.5, 114.5, 90, 'F'), 'D71': (166.5, 118.0, 0, 'F'),
    'JP1': (181.0, 110.0, 90, 'F'), 'C7': (183.5, 114.5, 0, 'F'),
    'TP4': (178.0, 124.0, 0, 'F'), 'TP5': (182.0, 124.0, 0, 'F'), 'TP6': (186.0, 124.0, 0, 'F'),
    'TP7': (190.0, 124.0, 0, 'F'),

    # ---- 12/24 V pump side (right) ----
    # input: barrel + screw terminal on the edge, fuse, reverse block, TVS, bulk, LED
    'J9': (211.5, Y1 - 13.7, 0, 'F'), 'J10': (223.5, MKDS_Y, 0, 'F'),
    'F1': (213.0, 153.0, 0, 'F'), 'D1': (224.0, 153.0, 180, 'F'), 'D2': (224.0, 158.0, 0, 'F'),
    'C1': (230.5, 153.0, 90, 'F'), 'C2': (233.5, 153.0, 90, 'F'),
    'R73': (230.5, 158.5, 0, 'F'), 'D3': (234.5, 158.5, 0, 'F'), 'TP1': (220.0, 147.0, 0, 'F'),

    # high-float relay chain
    'K1': (222.0, 112.0, 0, 'F'), 'D4': (209.0, 116.0, 90, 'F'), 'F2': (241.0, 156.0, 0, 'F'),
    'J11': (237.0, MKDS_Y, 0, 'F'),
    'R74': (236.0, 117.0, 90, 'F'), 'D5': (236.0, 122.0, 90, 'F'), 'U4': (238.5, 132.0, 0, 'F'),
    'R75': (244.0, 124.0, 90, 'F'),

    # pump B (brushed)
    'J12': (256.0, MKDS_Y, 0, 'F'), 'D6': (258.5, 162.0, 0, 'F'), 'Q1': (264.5, 155.0, 0, 'F'),
    'R76': (264.5, 150.5, 0, 'F'), 'R77': (268.5, 155.0, 90, 'F'),
    'R78': (253.0, 152.0, 90, 'F'), 'D7': (253.0, 156.5, 90, 'F'),
    'TP2': (262.0, 145.0, 0, 'F'), 'TP3': (270.5, 150.5, 0, 'F'),

    # pump A (stepstick + motor)
    'J13': (255.0, 110.0, 0, 'F'), 'J14': (267.7, 110.0, 0, 'F'),
    'JP2': (247.0, 111.0, 90, 'F'), 'JP3': (247.0, 116.0, 90, 'F'), 'JP4': (247.0, 122.0, 90, 'F'),
    'R79': (247.0, 126.5, 90, 'F'),
    'C3': (275.0, 116.0, 0, 'F'), 'C4': (272.0, 108.5, 90, 'F'),
    'J15': (267.0, Y1 - 4.0, 0, 'F'),
}
# level channels: one column above each jack (connector end at the bottom)
for n in range(1, 7):
    cx = JACK_X0 + JACK_P * (n - 1)
    P['J%d' % (n + 2)] = (cx, JACK_Y, 90, 'F')
    P['R%d0' % n] = (cx, 135.0, 90, 'F')      # R_PWR 100R
    P['R%d1' % n] = (cx, 139.0, 90, 'F')      # R_PU 10k
    P['R%d4' % n] = (cx + 3.0, 159.0, 90, 'F')  # R2 link 0R
    P['D%d0' % n] = (cx - 3.0, 159.0, 90, 'F')  # ESD
    P['R%d2' % n] = (cx, 147.0, 90, 'F')      # R_SER 1k
    P['R%d3' % n] = (cx - 2.2, 151.5, 90, 'F')  # R_DN 20k (DNP)
    P['C%d0' % n] = (cx + 2.2, 151.5, 90, 'F')  # 100 nF

# extra footprints that are on the board only (not in the schematic)
EXTRA = {
    'H5': ('MountingHole:MountingHole_2.2mm_M2', oly(97.79, 185.42), 'Olimex MH1 standoff'),
    'H6': ('MountingHole:MountingHole_2.2mm_M2', oly(92.71, 117.475), 'Olimex MH2 standoff'),
    'H7': ('MountingHole:MountingHole_2.2mm_M2', oly(115.57, 117.475), 'Olimex MH3 standoff'),
}
SHIELD_NET = 'GND'
REF_AT = {}                     # silk reference positions moved off neighbours: ref -> (x, y)


def parse_netlist(path):
    t = open(path).read()
    comps = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(footprint "([^"]*)"\)(.*?)\(sheetpath', t, re.S):
        dnp = '(property (name "dnp")' in m.group(4)
        comps[m.group(1)] = (m.group(2), m.group(3), dnp)
    pads = {}
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]*)"\)(.*?)(?=\(net \(code|\Z)', t, re.S):
        for r, p in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2)):
            pads[(r, p)] = m.group(1)
    return comps, pads


def load_fp(fpid):
    lib, name = fpid.split(':', 1)
    path = os.path.join(PROJ, 'calyx-level.pretty') if lib == 'calyx-level' else os.path.join(SYSLIB, lib + '.pretty')
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        sys.exit('footprint not found: ' + fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def seg(board, layer, a, b, w=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(layer)
    s.SetStart(pcbnew.VECTOR2I(MM(a[0]), MM(a[1])))
    s.SetEnd(pcbnew.VECTOR2I(MM(b[0]), MM(b[1])))
    s.SetWidth(MM(w))
    board.Add(s)


def rect(board, layer, x0, y0, x1, y1, w=0.1):
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        seg(board, layer, a, b, w)


def text(board, layer, s, x, y, size=1.0, rot=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetLayer(layer)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(size * 0.15))
    if rot:
        t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def keepout(board, x0, y0, x1, y1, name, parts_only=False):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowCopperPour(not parts_only)
    z.SetDoNotAllowTracks(not parts_only)
    z.SetDoNotAllowVias(not parts_only)
    z.SetDoNotAllowPads(parts_only)
    z.SetDoNotAllowFootprints(parts_only)
    z.SetZoneName(name)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    o = z.Outline()
    o.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(MM(x), MM(y))
    board.Add(z)


def main():
    netfile = sys.argv[1] if len(sys.argv) > 1 else '/tmp/cl.net'
    comps, padnets = parse_netlist(netfile)
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)

    nets = {}

    def net(name):
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
            nets[name] = ni
        return nets[name]

    missing = sorted(set(comps) - set(P))
    if missing:
        sys.exit('no placement for: ' + ' '.join(missing))

    for ref, (value, fpid, dnp) in sorted(comps.items()):
        fp = load_fp(fpid)
        fp.SetReference(ref)
        fp.SetValue(value)
        x, y, rot, side = P[ref]
        board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        fp.SetOrientationDegrees(rot)
        if ref.startswith('H') or ref[0] == 'J' and ref not in ('J1', 'J2'):   # connectors get silk labels
            fp.Reference().SetVisible(False)
        if ref.startswith('TP'):          # label test points with their signal, not TPn
            fp.Reference().SetVisible(False)
            fp.Value().SetLayer(pcbnew.F_SilkS)
            fp.Value().SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
            fp.Value().SetTextThickness(MM(0.12))
            fp.Value().SetPosition(pcbnew.VECTOR2I(MM(x), MM(y - 1.7)))
        if ref in REF_AT:
            fp.Reference().SetPosition(pcbnew.VECTOR2I(MM(REF_AT[ref][0]), MM(REF_AT[ref][1])))
        if side == 'B':
            fp.Flip(fp.GetPosition(), False)
        if dnp:
            fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
            fp.Value().SetText(value + ' DNP')
        for pad in fp.Pads():
            num = pad.GetNumber()
            if (ref, num) in padnets:
                pad.SetNet(net(padnets[(ref, num)]))
            elif num == 'SH':
                pad.SetNet(net(SHIELD_NET))
            if pad.GetNetname() == 'GND':
                pad.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)   # solid to the pours

    for ref, (fpid, (x, y), note) in EXTRA.items():
        fp = load_fp(fpid)
        fp.SetReference(ref)
        fp.SetValue(note)
        fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
                         | pcbnew.FP_BOARD_ONLY)
        board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))

    # outline and Olimex silhouette (it overhangs the top edge by about 22 mm: antenna off the board)
    rect(board, pcbnew.Edge_Cuts, X0, Y0, X1, Y1, 0.1)
    ox0, oy0 = oly(90.15, 90.0)
    ox1, oy1 = oly(118.15, 188.15)
    rect(board, pcbnew.Dwgs_User, ox0, oy0, ox1, oy1, 0.1)
    rect(board, pcbnew.F_Fab, ox0, Y0, ox1, oy1, 0.1)
    text(board, pcbnew.Dwgs_User, 'OLIMEX ESP32-POE-ISO (on top)', (ox0 + ox1) / 2 - 5, 150, 1.2, 90)
    text(board, pcbnew.Dwgs_User, 'antenna overhangs', (ox0 + ox1) / 2, 92, 1.0)
    keepout(board, 112.5, 112.5, 131.5, 174.0, 'no parts under Olimex', parts_only=True)
    text(board, pcbnew.F_SilkS, 'NO PARTS UNDER OLIMEX', (ox0 + ox1) / 2, 150, 1.0, 90)

    S = pcbnew.F_SilkS
    text(board, S, 'CALYX-LEVEL  rev A', 165.0, 127.0, 1.5)
    text(board, S, 'Corallite Labs', 165.0, 130.0, 1.0)
    text(board, S, 'ETHERNET', (ox0 + ox1) / 2, Y1 - 1.6, 1.0)
    for n, name in enumerate(('LVL A', 'LVL B', 'RO LOW', 'LEAK', 'SPARE 1', 'SPARE 2')):
        text(board, S, name, JACK_X0 + JACK_P * n, 163.2, 0.9)
    text(board, S, 'LEVEL JACKS  T=SIG R1=PWR R2,S=GND', 171.0, 131.5 + 0.0, 0.8)
    text(board, S, 'JP1: 1-2 3V3  2-3 5V', 181.0, 106.5, 0.8)
    text(board, S, 'SENS', 181.0, 107.8 + 4.5, 0.7)
    text(board, S, 'PUMP SUPPLY 12-24V', 218.0, 162.5, 0.9)
    text(board, S, '+    -', 226.0, 168.6, 0.9)
    text(board, S, 'HIGH FLOAT', 242.0, 165.4, 0.9)
    text(board, S, 'V   RET   SH', 242.0, 168.6, 0.9)
    text(board, S, 'PUMP', 258.5, 165.4, 0.9)
    text(board, S, '+    -', 258.5, 168.6, 0.9)
    text(board, S, 'MOTOR', 270.75, 171.0, 0.9)
    text(board, S, 'HIGH-FLOAT RELAY', 222.0, 134.0, 0.9)
    text(board, S, 'cuts pump power', 222.0, 135.4, 0.8)
    text(board, S, 'STEPSTICK  TMC2209', 261.35, 131.0, 0.9)
    text(board, S, 'MS1', 243.8, 111.0, 0.7)
    text(board, S, 'MS2', 243.8, 116.0, 0.7)
    text(board, S, 'A4988', 243.5, 122.0, 0.7)
    text(board, S, 'BUILD B: R76  A: R79', 262.0, 140.5, 0.8)
    text(board, pcbnew.B_SilkS, 'Calyx-Level carrier rev A  github.com/ballhog/calyx-level', 200, 135, 1.0)

    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)

    pcbnew.SaveBoard(PCB, board, True)   # True: leave the .kicad_pro alone
    print('wrote %s: %d footprints, %d nets' % (os.path.relpath(PCB), len(list(board.GetFootprints())), len(nets)))


if __name__ == '__main__':
    main()
