#!/usr/bin/env python3
"""Autoroute the carrier with Freerouting, add GND pours, run DRC.

    python3 hardware/tools/gen_pcb.py /tmp/cl.net         # fresh, unrouted board
    python3 hardware/tools/route_pcb.py [path/to/freerouting.jar]

Steps: export Specctra DSN -> Freerouting (headless) ->
read the .ses back (KiCad 7's ImportSpecctraSES only works inside the GUI, so the
session is parsed here) -> GND pour on both layers -> zone fill -> DRC report.

Writes calyx-level-carrier.kicad_pcb in place and drc.rpt beside it.
"""
import os
import re
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(HERE, '..', 'calyx-level-carrier')
PCB = os.path.join(PROJ, 'calyx-level-carrier.kicad_pcb')
WORK = os.environ.get('CF_WORK', '/tmp/cl-route')
JAR = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('FREEROUTING_JAR', '/home/claude/fr/freerouting.jar')
MM = pcbnew.FromMM


def tokens(txt):
    return re.findall(r'\(|\)|"[^"]*"|[^\s()]+', txt)


def tree(tok):
    stack = [[]]
    for t in tok:
        if t == '(':
            stack.append([])
        elif t == ')':
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t.strip('"'))
    return stack[0][0]


def find(node, key):
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            yield c


def import_ses(board, path):
    root = tree(tokens(open(path).read()))
    routes = next(find(root, 'routes'))
    res = next(find(routes, 'resolution'))
    unit, per = res[1], float(res[2])
    scale = {'um': 0.001, 'mm': 1.0, 'mil': 0.0254, 'inch': 25.4}[unit] / per

    def P(x, y):           # Specctra y is up
        return pcbnew.VECTOR2I(MM(float(x) * scale), MM(-float(y) * scale))

    layers = {'F.Cu': pcbnew.F_Cu, 'B.Cu': pcbnew.B_Cu}
    netcode = {n.GetNetname(): n for n in board.GetNetInfo().NetsByName().values()}
    ntracks = nvias = 0
    nw = next(find(routes, 'network_out'))
    for net in find(nw, 'net'):
        ni = netcode[net[1]]
        for w in find(net, 'wire'):
            path_ = next(find(w, 'path'))
            layer, width = layers[path_[1]], float(path_[2]) * scale
            pts = path_[3:]
            xy = [(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
            for a, b in zip(xy, xy[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(P(*a))
                t.SetEnd(P(*b))
                t.SetWidth(MM(width))
                t.SetLayer(layer)
                t.SetNet(ni)
                board.Add(t)
                ntracks += 1
        for v in find(net, 'via'):
            m = re.search(r'(\d+):(\d+)_um', v[1])
            dia, drill = (int(m.group(1)) / 1000.0, int(m.group(2)) / 1000.0) if m else (0.6, 0.3)
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(P(v[2], v[3]))
            via.SetWidth(MM(dia))
            via.SetDrill(MM(drill))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNet(ni)
            board.Add(via)
            nvias += 1
    return ntracks, nvias


def via_links(board, via):
    """Tracks ending on a via plus pads under it."""
    p = via.GetPosition()
    n = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetCode() == via.GetNetCode()
            and min((t.GetStart() - p).EuclideanNorm(), (t.GetEnd() - p).EuclideanNorm()) <= via.GetWidth() // 2)
    n += sum(1 for pad in board.GetPads() if pad.GetNetCode() == via.GetNetCode() and pad.HitTest(p))
    return n


def prune_dangling(board):
    """Drop track segments with an end that touches nothing on its net (Freerouting leaves a few stubs)."""
    removed = 0
    seen = set()
    for t in list(board.GetTracks()):         # out-and-back duplicates hide a stub from the end count
        if t.Type() != pcbnew.PCB_TRACE_T:
            continue
        a, b = (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)
        key = (min(a, b), max(a, b), t.GetLayer(), t.GetNetCode())
        if key in seen or a == b:
            board.Remove(t)
            removed += 1
        seen.add(key)
    while True:                               # then let KiCad's connectivity find dead ends
        board.BuildConnectivity()
        conn = board.GetConnectivity()
        gone = [t for t in board.GetTracks()
                if (t.Type() == pcbnew.PCB_TRACE_T and conn.TestTrackEndpointDangling(t, False))
                or (t.Type() == pcbnew.PCB_VIA_T and via_links(board, t) < 2)]
        if not gone:
            return removed
        for t in gone:
            board.Remove(t)
        removed += len(gone)


def gnd_pour(board, layer):
    bb = board.GetBoardEdgesBoundingBox()
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet('GND'))
    z.SetLocalClearance(MM(0.3))
    z.SetMinThickness(MM(0.25))
    z.SetThermalReliefGap(MM(0.4))
    z.SetThermalReliefSpokeWidth(MM(0.4))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetAssignedPriority(0)
    z.SetZoneName('GND ' + board.GetLayerName(layer))
    o = z.Outline()
    o.NewOutline()
    for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                 (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
        o.Append(x, y)
    board.Add(z)


COPPER_ERRORS = ('clearance', 'unconnected_items', 'track_dangling', 'shorting_items', 'tracks_crossing',
                 'hole_clearance', 'copper_edge_clearance', 'starved_thermal', 'via_dangling',
                 'annular_width', 'track_width', 'via_diameter', 'drill_out_of_range')


def route_once(attempt):
    board = pcbnew.LoadBoard(PCB)
    # Start from gen_pcb.py's unrouted board. (Stripping a routed board here would be neater, but
    # removing items from a loaded board breaks KiCad 7's SWIG wrappers.)
    if len(board.GetTracks()) or any(not board.GetArea(i).GetIsRuleArea() for i in range(board.GetAreaCount())):
        sys.exit('board is already routed: run gen_pcb.py first (or route by hand in KiCad)')

    dsn, ses = os.path.join(WORK, 'cl.dsn'), os.path.join(WORK, 'cl.ses')
    if os.path.exists(ses):
        os.remove(ses)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit('DSN export failed')
    cmd = ['xvfb-run', '-a', 'java', '-jar', JAR, '-de', dsn, '-do', ses, '-mp', os.environ.get('FR_PASSES', '20'), '-host', 'calyx-level']
    subprocess.run(cmd, check=False, timeout=1200, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(ses):
        sys.exit('Freerouting produced no session file')
    nt, nv = import_ses(board, ses)
    pruned = prune_dangling(board)
    gnd_pour(board, pcbnew.F_Cu)
    gnd_pour(board, pcbnew.B_Cu)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    rpt = os.path.join(WORK, 'drc-%d.rpt' % attempt)
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    counts = {}
    for line in open(rpt):
        m = re.match(r'\[(\w+)\]', line)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    bad = sum(v for k, v in counts.items() if k in COPPER_ERRORS)
    print('attempt %d: %d segments, %d vias, %d pruned; DRC %s' % (
        attempt, nt, nv, pruned, ', '.join('%s %d' % kv for kv in sorted(counts.items())) or 'clean'), flush=True)
    return board, rpt, bad


def main():
    os.makedirs(WORK, exist_ok=True)
    for attempt in range(1, int(os.environ.get('FR_ATTEMPTS', '8')) + 1):
        board, rpt, bad = route_once(attempt)
        if not bad:
            break
    else:
        print('no copper-clean result in 8 attempts; saving the last one for hand fixing')
    pcbnew.SaveBoard(PCB, board, True)   # True: leave the .kicad_pro alone
    os.replace(rpt, os.path.join(PROJ, 'drc.rpt'))


if __name__ == '__main__':
    main()
