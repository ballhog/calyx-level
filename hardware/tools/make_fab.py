#!/usr/bin/env python3
"""JLCPCB fab outputs for the carrier: gerbers + drill (zipped), BOM and CPL for assembly.

    python3 hardware/tools/make_fab.py                 # -> hardware/calyx-level-carrier/fab/
    python3 hardware/tools/make_fab.py --preview DIR   # same files into DIR, placeholders allowed

Refuses to write real fab outputs while any footprint on the board is a PLACEHOLDER
(none on rev A), or while DRC reports copper errors.
--preview is for looking at the gerbers in a viewer, never for ordering.
"""
import csv
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(HERE, '..', 'calyx-level-carrier')
PCB = os.path.join(PROJ, 'calyx-level-carrier.kicad_pcb')
SCH = os.path.join(PROJ, 'calyx-level-carrier.kicad_sch')
LAYERS = 'F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts'
COPPER_ERRORS = ('clearance', 'unconnected_items', 'shorting_items', 'tracks_crossing', 'hole_clearance',
                 'copper_edge_clearance', 'annular_width', 'track_width', 'starved_thermal')


def cli(*args):
    subprocess.run(['kicad-cli'] + list(args), check=True, stdout=subprocess.DEVNULL)


def placeholders(board):
    return sorted(f.GetReference() for f in board.GetFootprints() if 'PLACEHOLDER' in f.GetDescription())


def copper_errors(board, rpt):
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    n = {}
    for line in open(rpt):
        m = re.match(r'\[(\w+)\]', line)
        if m and m.group(1) in COPPER_ERRORS:
            n[m.group(1)] = n.get(m.group(1), 0) + 1
    return n


def bom(netfile, out):
    t = open(netfile).read()
    rows = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(footprint "([^"]*)"\)(.*?)\(sheetpath',
                         t, re.S):
        ref, value, fp, rest = m.groups()
        if '(property (name "dnp")' in rest or ref[0] in 'H' or ref.startswith('TP'):
            continue
        lcsc = re.search(r'\(field \(name "LCSC"\) "([^"]*)"\)', rest)
        mpn = re.search(r'\(field \(name "MPN"\) "([^"]*)"\)', rest)
        key = (value, fp.split(':')[-1], lcsc.group(1) if lcsc else '', mpn.group(1) if mpn else '')
        rows.setdefault(key, []).append(ref)
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #', 'MPN'])
        for (value, fp, lcsc, mpn), refs in sorted(rows.items(), key=lambda kv: kv[1][0]):
            w.writerow([value, ','.join(sorted(refs)), fp, lcsc, mpn])
    missing = sum(1 for k in rows if not k[2])
    return len(rows), missing


def cpl(board, out):
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        for fp in sorted(board.GetFootprints(), key=lambda x: x.GetReference()):
            if fp.GetAttributes() & (pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_BOARD_ONLY):
                continue
            if not fp.GetAttributes() & pcbnew.FP_SMD:
                continue
            p = fp.GetPosition()
            w.writerow([fp.GetReference(), '%.3fmm' % pcbnew.ToMM(p.x), '%.3fmm' % -pcbnew.ToMM(p.y),
                        'Top' if fp.GetLayer() == pcbnew.F_Cu else 'Bottom', '%.1f' % fp.GetOrientationDegrees()])


def main():
    preview = None
    if len(sys.argv) > 2 and sys.argv[1] == '--preview':
        preview = os.path.abspath(sys.argv[2])
    out = preview or os.path.join(PROJ, 'fab')
    board = pcbnew.LoadBoard(PCB)

    ph = placeholders(board)
    if ph and not preview:
        sys.exit('refusing: placeholder footprint(s) on the board: %s. Replace with the vendor footprint first '
                 '(see hardware/DESIGN.md), or use --preview DIR to look at the gerbers.' % ', '.join(ph))
    errs = copper_errors(board, '/tmp/cl-fab-drc.rpt')
    if errs and not preview:
        sys.exit('refusing: DRC copper errors %s (see /tmp/cl-fab-drc.rpt)' % errs)

    if os.path.isdir(out):
        shutil.rmtree(out)
    gdir = os.path.join(out, 'gerbers')
    os.makedirs(gdir)
    cli('pcb', 'export', 'gerbers', '--layers', LAYERS, '--no-x2', '--subtract-soldermask', '-o', gdir + '/', PCB)
    cli('pcb', 'export', 'drill', '--format', 'excellon', '--excellon-separate-th', '--generate-map',
        '--map-format', 'gerberx2', '-o', gdir + '/', PCB)
    zname = os.path.join(out, 'calyx-level-carrier-gerbers%s.zip' % ('-PREVIEW-NOT-FOR-ORDER' if preview else ''))
    with zipfile.ZipFile(zname, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gdir)):
            z.write(os.path.join(gdir, f), f)

    net = os.path.join(out, 'calyx-level-carrier.net')
    cli('sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', net, SCH)
    lines, missing = bom(net, os.path.join(out, 'calyx-level-carrier-bom-jlc.csv'))
    os.remove(net)
    cpl(board, os.path.join(out, 'calyx-level-carrier-cpl-jlc.csv'))
    print('wrote %s (%d BOM lines, %d without an LCSC number)%s' % (
        os.path.relpath(out), lines, missing, '  PREVIEW: placeholders %s' % ph if ph else ''))


if __name__ == '__main__':
    main()
