#!/usr/bin/env python3
"""Generate the Calyx-Level carrier rev A schematic.

Writes hardware/calyx-level-carrier/calyx-level-carrier.kicad_sch in KiCad 7
format (opens in KiCad 8/9/10, which upgrade it on save). Symbols are copied
from the stock KiCad symbol library so the file is self-contained.

Every pin gets a short wire stub ending in a net label (or a power symbol), so
connectivity is defined by net names, not by hand-drawn wiring. That keeps the
generator simple and makes the netlist check (check_netlist.py) exact.

    python3 hardware/tools/gen_schematic.py [--lib /usr/share/kicad/symbols]

Design notes and the reasoning behind each block: hardware/DESIGN.md
"""
import argparse
import os
import re
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, '..', 'calyx-level-carrier')
PROJECT = 'calyx-level-carrier'
NS = uuid.UUID('6c1f3a52-7d0e-4c55-9a0b-ca17e7e10000')  # fixed: stable UUIDs across runs

GRID = 1.27
STUB = 2.54

# ----------------------------------------------------------------- library


class Lib:
    def __init__(self, root):
        self.root = root
        self.cache = {}

    def text(self, lib):
        if lib not in self.cache:
            self.cache[lib] = open(os.path.join(self.root, lib + '.kicad_sym')).read()
        return self.cache[lib]

    @staticmethod
    def _block(txt, start):
        depth, j = 0, start
        while True:
            c = txt[j]
            if c == '"':
                j += 1
                while txt[j] != '"':
                    if txt[j] == '\\':
                        j += 1
                    j += 1
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    return txt[start:j + 1]
            j += 1

    def raw(self, lib, name):
        txt = self.text(lib)
        i = txt.index('\n  (symbol "%s"' % name) + 3
        return self._block(txt, i)

    def flat(self, lib, name):
        """Symbol text with `extends` resolved, renamed to "lib:name"."""
        blk = self.raw(lib, name)
        m = re.search(r'\(extends "([^"]+)"\)', blk)
        if m:
            parent = m.group(1)
            pblk = self.raw(lib, parent)
            # child's own properties override the parent's
            props = dict(re.findall(r'\(property "([^"]+)" ("(?:[^"\\]|\\.)*")', blk))
            out = pblk
            for k, v in props.items():
                out = re.sub(r'(\(property "%s" )"(?:[^"\\]|\\.)*"' % re.escape(k),
                             lambda mm: mm.group(1) + v, out, count=1)
            out = out.replace('(symbol "%s_' % parent, '(symbol "%s_' % name)
            out = out.replace('(symbol "%s"' % parent, '(symbol "%s"' % name, 1)
            blk = out
        blk = blk.replace('(symbol "%s"' % name, '(symbol "%s:%s"' % (lib, name), 1)
        return blk

    def props(self, lib, name):
        """Reference/Value positions from the library: {key: (x, y, angle, justify)}."""
        blk = self.flat(lib, name)
        out = {}
        for k in ('Reference', 'Value'):
            m = re.search(r'\(property "%s" "(?:[^"\\]|\\.)*" \(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)' % k, blk)
            just = ''
            if m:
                eff = self._block(blk, blk.index('(effects', m.end()))
                jm = re.search(r'\(justify ([^)]*)\)', eff)
                just = jm.group(1) if jm else ''
                out[k] = (float(m.group(1)), float(m.group(2)), float(m.group(3)), just)
        return out

    def pins(self, lib, name):
        blk = self.flat(lib, name)
        out = []
        for um in re.finditer(r'\(symbol "%s_(\d+)_(\d+)"' % re.escape(name), blk):
            ublk = self._block(blk, um.start())
            unit = int(um.group(1))
            for pm in re.finditer(r'\(pin (\w+) \w+ \(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)', ublk):
                pblk = self._block(ublk, pm.start())
                num = re.search(r'\(number "([^"]*)"', pblk).group(1)
                out.append(dict(unit=unit, type=pm.group(1), x=float(pm.group(2)),
                                y=float(pm.group(3)), rot=float(pm.group(4)), num=num))
        return out


# ----------------------------------------------------------------- writer


def uid(*parts):
    return str(uuid.uuid5(NS, '/'.join(str(p) for p in parts)))


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def snap(v):
    return round(round(v / GRID) * GRID, 4)


def rot(px, py, a):
    """Rotate a symbol-space point (y up) counter-clockwise by a degrees."""
    a %= 360
    return {0: (px, py), 90: (-py, px), 180: (-px, -py), 270: (py, -px)}[a]


POWER_SYMS = {'GND': 'GND', '+3V3': '+3V3', '+5V': '+5V'}


class Sheet:
    def __init__(self, lib):
        self.lib = lib
        self.used = {}           # "lib:name" -> flat text
        self.items = []
        self.root = uid('root')
        self.pwr_n = 0
        self.intended = {}       # net -> set of "REF.pin"
        self.refs = set()

    # --- primitives
    def _use(self, lib, name):
        key = '%s:%s' % (lib, name)
        if key not in self.used:
            self.used[key] = self.lib.flat(lib, name)

    def wire(self, x1, y1, x2, y2):
        self.items.append('  (wire (pts (xy %g %g) (xy %g %g))\n    (stroke (width 0) (type default))\n'
                          '    (uuid %s)\n  )' % (x1, y1, x2, y2, uid('w', x1, y1, x2, y2)))

    def label(self, net, x, y, angle):
        just = {0: 'left bottom', 90: 'left bottom', 180: 'right bottom', 270: 'right bottom'}[angle]
        self.items.append('  (label %s (at %g %g %d) (fields_autoplaced)\n'
                          '    (effects (font (size 1.27 1.27)) (justify %s))\n    (uuid %s)\n  )'
                          % (q(net), x, y, angle, just, uid('l', net, x, y)))

    def no_connect(self, x, y):
        self.items.append('  (no_connect (at %g %g) (uuid %s))' % (x, y, uid('nc', x, y)))

    def text(self, s, x, y, size=1.27):
        self.items.append('  (text %s (at %g %g 0)\n    (effects (font (size %g %g)) (justify left top))\n'
                          '    (uuid %s)\n  )' % (q(s), x, y, size, size, uid('t', s[:40], x, y)))

    def _symbol(self, lib, name, ref, value, x, y, unit, fields, pin_nums, in_bom=True,
                on_board=True, dnp=False, hide_ref=False, hide_val=False, angle=0):
        self._use(lib, name)
        lp = self.lib.props(lib, name)
        props = []
        for k, v, hide in (('Reference', ref, hide_ref), ('Value', value, hide_val)):
            lx, ly, la, just = lp.get(k, (0, 0, 0, ''))
            rx, ry = rot(lx, ly, angle)
            ta = 0 if (la + angle) % 180 == 0 else 90
            props.append((k, v, x + rx, y - ry, ta, just, hide))
        for k, v in fields.items():
            props.append((k, v, x, y, 0, '', True))
        p = []
        for k, v, px, py, ta, just, hide in props:
            p.append('    (property %s %s (at %g %g %d)\n      (effects (font (size 1.27 1.27))%s%s)\n    )'
                     % (q(k), q(v), px, py, ta, (' (justify %s)' % just) if just else '',
                        ' hide' if hide else ''))
        pins = '\n'.join('    (pin %s (uuid %s))' % (q(n), uid('p', ref, unit, n)) for n in pin_nums)
        self.items.append(
            '  (symbol (lib_id %s) (at %g %g %d) (unit %d)\n'
            '    (in_bom %s) (on_board %s) (dnp %s)\n    (uuid %s)\n%s\n%s\n'
            '    (instances\n      (project %s\n        (path "/%s"\n'
            '          (reference %s) (unit %d)\n        )\n      )\n    )\n  )'
            % (q('%s:%s' % (lib, name)), x, y, angle, unit, 'yes' if in_bom else 'no',
               'yes' if on_board else 'no', 'yes' if dnp else 'no', uid('s', ref, unit),
               '\n'.join(p), pins, q(PROJECT), self.root, q(ref), unit))

    def power(self, net, x, y):
        self.pwr_n += 1
        name = POWER_SYMS[net]
        self._symbol('power', name, '#PWR%03d' % self.pwr_n, net, x, y, 1, {'Footprint': '', 'Datasheet': ''},
                     ['1'], in_bom=False, on_board=False, hide_ref=True)

    def pwr_flag(self, net, x, y):
        self.pwr_n += 1
        ref = '#FLG%03d' % self.pwr_n
        self._symbol('power', 'PWR_FLAG', ref, 'PWR_FLAG', x, y, 1, {'Footprint': '', 'Datasheet': ''},
                     ['1'], in_bom=False, on_board=False, hide_ref=True)
        # PWR_FLAG pin is at its origin; stub down to the net
        self.wire(x, y, x, y + STUB)
        self._net_end(net, x, y + STUB, 270)

    def _net_end(self, net, x, y, angle):
        if net in POWER_SYMS:
            self.power(net, x, y)
        else:
            self.label(net, x, y, angle)

    # --- a placed part: nets = {pin_number: net | 'NC'}
    def part(self, lib, name, ref, value, x, y, nets, unit=1, fields=None, dnp=False, hide_val=False,
             angle=0):
        x, y = snap(x), snap(y)
        fields = dict(fields or {})
        fields.setdefault('Datasheet', '')
        allpins = [p for p in self.lib.pins(lib, name) if p['unit'] in (unit, 0)]
        self._symbol(lib, name, ref, value, x, y, unit, fields, [p['num'] for p in allpins], dnp=dnp,
                     hide_val=hide_val, angle=angle)
        self.refs.add(ref)
        missing = [p['num'] for p in allpins if p['num'] not in nets]
        if missing:
            raise SystemExit('%s: pins with no net assigned: %s' % (ref, missing))
        for p in allpins:
            net = nets[p['num']]
            rx, ry = rot(p['x'], p['y'], angle)
            ex, ey = round(x + rx, 4), round(y - ry, 4)
            if net == 'NC':
                self.no_connect(ex, ey)
                continue
            r = int(p['rot'] + angle) % 360
            dx, dy = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[r]
            sx, sy = ex + dx * STUB, ey + dy * STUB
            self.wire(ex, ey, sx, sy)
            lab_angle = {(-1, 0): 180, (1, 0): 0, (0, 1): 270, (0, -1): 90}[(dx, dy)]
            self._net_end(net, sx, sy, lab_angle)
            self.intended.setdefault(net, set()).add('%s.%s' % (ref, p['num']))

    def write(self, path, title):
        libs = '\n'.join('    ' + t.replace('\n', '\n  ') for t in self.used.values())
        tb = ('  (title_block\n    (title %s)\n    (date "2026-10-26")\n    (rev "A")\n'
              '    (company "Corallite Labs")\n'
              '    (comment 1 "Carrier for Olimex ESP32-POE-ISO: 6 level jacks, hardwired high-float cutoff, brushed or stepper ATO pump")\n'
              '    (comment 2 "Generated by hardware/tools/gen_schematic.py; see hardware/DESIGN.md")\n'
              '  )\n') % q(title)
        body = ('(kicad_sch (version 20230121) (generator eeschema)\n\n  (uuid %s)\n\n  (paper "A3")\n\n%s\n'
                '  (lib_symbols\n%s\n  )\n\n%s\n\n  (sheet_instances\n    (path "/" (page "1"))\n  )\n)\n'
                % (self.root, tb, libs, '\n'.join(self.items)))
        with open(path, 'w') as f:
            f.write(body)


# ----------------------------------------------------------------- the design

R0603 = 'Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder'
R1206 = 'Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder'
C0603 = 'Capacitor_SMD:C_0603_1608Metric_Pad1.08x0.95mm_HandSolder'
C0805 = 'Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder'
C1206 = 'Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder'
LED0603 = 'LED_SMD:LED_0603_1608Metric'
SOT23 = 'Package_TO_SOT_SMD:SOT-23'
SOD123 = 'Diode_SMD:D_SOD-123'
SOD323 = 'Diode_SMD:D_SOD-323'
SMA = 'Diode_SMD:D_SMA'
TP = {'Footprint': 'TestPoint:TestPoint_Pad_D1.5mm'}
MKDS2 = 'TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal'
MKDS3 = 'TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal'

# Olimex ESP32-POE-ISO extension headers (pinout as in calyx-flow, from OLIMEX/ESP32-POE-ISO Rev O).
# Signal names and GPIOs follow docs/schematic.md section 1 (the v1 pin map, frozen).
EXT1 = ['+5V', '+3V3', 'GND', 'NC', 'NC', 'NC', 'BUZZER', 'NC', 'SPARE_IN2', 'HIGH_FLOAT_SENSE']
#        5V     3V3     GND   EN    IO0   IO1   IO2       IO3   IO4          IO5
EXT2 = ['LVL_B', 'LVL_A', 'RO_LOW', 'NC', 'SPARE_IN1', 'LEAK', 'PUMP_EN', 'STATUS_LED', 'DIR', 'STEP']
#        GPI39    GPI36    GPI35    GPI34 IO33         IO32    IO16       IO15          IO14   IO13

# level jacks: (channel, GPIO net, silk name)
LEVEL = [(1, 'LVL_A', 'LVL A'), (2, 'LVL_B', 'LVL B'), (3, 'RO_LOW', 'RO LOW'), (4, 'LEAK', 'LEAK'),
         (5, 'SPARE_IN1', 'SPARE 1'), (6, 'SPARE_IN2', 'SPARE 2')]


def build(sheet):
    s = sheet
    T = s.text

    T('CALYX-LEVEL CARRIER  rev A   (Corallite Labs)\n'
      'Plugs onto an Olimex ESP32-POE-ISO (WROOM) via EXT1/EXT2. One board for every role (sensor / pump / single):\n'
      '6 level jacks (3.5 mm), high-level float that cuts pump power through a relay (no firmware in that path),\n'
      'brushed pump on a MOSFET (pump B) or a TMC2209 stepstick (pump A).  Notes: hardware/DESIGN.md, docs/schematic.md', 20, 16, 1.5)

    # ================= A: Olimex headers (x 15-85, y 45-175)
    T('OLIMEX ESP32-POE-ISO (WROOM)\nEXT1/EXT2: 1x10, 2.54 mm, 25.4 mm apart.\nCarrier: female sockets. Olimex: male headers.\n'
      'Boot straps: GPIO 0/2/5/12/15.\nGPI39/GPI35: check the Olimex sense jumpers are open.', 20, 45)
    sock = {'Footprint': 'Connector_PinSocket_2.54mm:PinSocket_1x10_P2.54mm_Vertical',
            'Description': 'Olimex ESP32-POE-ISO header socket'}
    s.part('Connector_Generic', 'Conn_01x10', 'J1', 'EXT1', 50.8, 86.36,
           {str(i + 1): n for i, n in enumerate(EXT1)}, fields=sock)
    T('1 +5V  2 +3V3  3 GND  4 EN  5 IO0\n6 IO1/TX0  7 IO2 = BUZZER  8 IO3/RX0\n9 IO4 = SPARE_IN2  10 IO5 = HIGH_FLOAT_SENSE',
      20, 103)
    s.part('Connector_Generic', 'Conn_01x10', 'J2', 'EXT2', 50.8, 137.16,
           {str(i + 1): n for i, n in enumerate(EXT2)}, fields=sock)
    T('1 GPI39 = LVL_B  2 GPI36 = LVL_A  3 GPI35 = RO_LOW\n4 GPI34 (BUT1, on the Olimex)  5 IO33 = SPARE_IN1\n'
      '6 IO32 = LEAK  7 IO16 = PUMP_EN  8 IO15 = STATUS_LED\n9 IO14 = DIR  10 IO13 = STEP', 20, 154)
    for i, n in enumerate(['+5V', '+3V3', 'GND']):
        s.pwr_flag(n, 66.04 + i * 7.62, 50.8)

    # ================= B: level jacks (x 95-300, y 40-160)
    T('LEVEL JACKS x6 (3.5 mm 4-pole; a 3-pole TRS plug works too: its sleeve lands on R2 + S)\n'
      'T = signal, R1 = sensor supply (SENS_V through 100R, so a plug shorting during insertion can\'t pull the rail down),\n'
      'R2 = GND through 0R (remove if an Apex plug uses R2), S = GND.  VERIFY the Apex pinout before plugging Apex sensors in.\n'
      'Default: 10k pull-up to 3V3 + 1k series + 100n (floats, open-collector or 3.3 V outputs; reads low = closed).\n'
      '5 V push-pull sensor: R_PU DNP, R_SER 10k, R_DN 20k fitted -> 5 V reads 3.33 V.', 95, 40)
    for n, gpio, _ in LEVEL:
        y0 = 72.39 + (n - 1) * 15.24
        tip, pwr, r2 = 'L%d_TIP' % n, 'L%d_PWR' % n, 'L%d_R2' % n
        b = 10 * n
        s.part('Connector_Audio', 'AudioJack4', 'J%d' % (n + 2), gpio, 104.14, y0,
               {'T': tip, 'R1': pwr, 'R2': r2, 'S': 'GND'},
               fields={'Footprint': 'Connector_Audio:Jack_3.5mm_KoreanHropartsElec_PJ-320D-4A_Horizontal',
                       'LCSC': 'C95562', 'MPN': 'PJ-320D-4A', 'Manufacturer': 'Korean Hroparts Elec'})
        s.part('Device', 'R', 'R%d' % (b + 0), '100R', 132.08, y0 - 2.54, {'1': 'SENS_V', '2': pwr}, angle=90,
               fields={'Footprint': R0603, 'Notes': 'R_PWR: limits a ring-to-sleeve short while a plug goes in'})
        s.part('Device', 'R', 'R%d' % (b + 4), '0R', 149.86, y0 + 2.54, {'1': r2, '2': 'GND'}, angle=90,
               fields={'Footprint': R0603, 'Notes': 'R2 link: jack ring 2 to GND; remove if a sensor plug uses R2'})
        s.part('Device', 'R', 'R%d' % (b + 1), '10k', 167.64, y0 - 3.81, {'1': '+3V3', '2': tip},
               fields={'Footprint': R0603, 'Notes': 'R_PU: DNP for a 5 V push-pull sensor'})
        s.part('Device', 'D_TVS', 'D%d' % (b + 0), 'PESD5V0S1BL', 180.34, y0 + 3.81, {'1': tip, '2': 'GND'},
               angle=90, fields={'Footprint': SOD323, 'MPN': 'PESD5V0S1BL', 'Manufacturer': 'Nexperia',
                                 'Notes': 'ESD on the cable'})
        s.part('Device', 'R', 'R%d' % (b + 2), '1k', 200.66, y0, {'1': tip, '2': gpio}, angle=90,
               fields={'Footprint': R0603, 'Notes': 'R_SER: 10k for a 5 V sensor (with R_DN)'})
        s.part('Device', 'R', 'R%d' % (b + 3), '20k', 218.44, y0 + 3.81, {'1': gpio, '2': 'GND'}, dnp=True,
               fields={'Footprint': R0603, 'Notes': 'R_DN: DNP; fit with R_SER 10k for a 5 V push-pull sensor'})
        s.part('Device', 'C', 'C%d' % (b + 0), '100nF', 233.68, y0 + 3.81, {'1': gpio, '2': 'GND'},
               fields={'Footprint': C0603})

    T('SENSOR SUPPLY (SENS_V)\nJP1 picks 3V3 or 5V\nfor all six jacks.\nDefault 3V3.', 255, 50)
    s.part('Jumper', 'Jumper_3_Open', 'JP1', 'SENS_V', 266.7, 72.39, {'1': '+3V3', '2': 'SENS_V', '3': '+5V'},
           fields={'Footprint': 'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical',
                   'Notes': '1-2 = 3V3, 2-3 = 5V'})
    s.part('Device', 'C', 'C7', '10uF', 284.48, 81.28, {'1': 'SENS_V', '2': 'GND'}, fields={'Footprint': C0805})

    # ================= C: status LED + buzzer (x 15-90, y 185-280)
    T('STATUS LED (IO15) and BUZZER (IO2)\nBoth are boot straps: the LED and the base\npull-down hold them low at reset, which is\nwhat the ESP32 wants (IO15 low only mutes\nthe ROM boot log).', 20, 185)
    s.part('Device', 'R', 'R70', '330R', 30.48, 222.25, {'1': 'STATUS_LED', '2': 'LED_ST'},
           fields={'Footprint': R0603})
    s.part('Device', 'LED', 'D70', 'BLUE', 30.48, 238.76, {'2': 'LED_ST', '1': 'GND'}, angle=90,
           fields={'Footprint': LED0603, 'Notes': 'status'})
    s.part('Device', 'R', 'R71', '1k', 48.26, 228.6, {'1': 'BUZZER', '2': 'BZ_B'}, angle=90,
           fields={'Footprint': R0603})
    s.part('Device', 'R', 'R72', '10k', 55.88, 241.3, {'1': 'BZ_B', '2': 'GND'}, fields={'Footprint': R0603})
    s.part('Transistor_BJT', 'MMBT3904', 'Q70', 'MMBT3904', 68.58, 228.6, {'1': 'BZ_B', '2': 'GND', '3': 'BZ_C'},
           fields={'Footprint': SOT23})
    s.part('Device', 'Buzzer', 'BZ1', '5V active', 68.58, 210.82, {'1': '+5V', '2': 'BZ_C'},
           fields={'Footprint': 'Buzzer_Beeper:Buzzer_12x9.5RM7.6',
                   'MPN': 'PUI AI-1223-TWT-5V-2-R (verify: 12 mm, 7.6 mm pitch, active 5 V)'})
    s.part('Device', 'D', 'D71', '1N4148W', 81.28, 210.82, {'1': '+5V', '2': 'BZ_C'}, angle=90,
           fields={'Footprint': SOD123})

    # ================= D: pump supply input (x 95-210, y 165-210)
    T('PUMP SUPPLY 12 or 24 V (to match the pump; default build 24 V)\n'
      'Barrel (PJ-102AH, 2.0 mm pin: Mean Well P1J plugs) or screw terminal, not both at once.\n'
      'Fuse -> reverse-polarity Schottky -> TVS.  The supply ground is the board GND: fine on the ISO board only.', 95, 165)
    s.part('Connector', 'Barrel_Jack_Switch', 'J9', 'PUMP SUPPLY', 101.6, 195.58,
           {'1': 'VIN_RAW', '2': 'GND', '3': 'NC'},
           fields={'Footprint': 'Connector_BarrelJack:BarrelJack_CUI_PJ-102AH_Horizontal', 'MPN': 'PJ-102AH',
                   'Manufacturer': 'Same Sky (CUI)'})
    s.part('Connector_Generic', 'Conn_01x02', 'J10', 'PUMP SUPPLY', 116.84, 213.36, {'1': 'VIN_RAW', '2': 'GND'},
           fields={'Footprint': MKDS2, 'MPN': 'MKDS 1,5/2-5,08 (1715721)', 'Manufacturer': 'Phoenix Contact'})
    s.part('Device', 'Fuse', 'F1', '2A', 124.46, 190.5, {'1': 'VIN_RAW', '2': 'VIN_F'}, angle=90,
           fields={'Footprint': 'Fuse:Fuseholder_Littelfuse_Nano2_154x',
                   'MPN': 'Littelfuse 0154002.DRT holder + 0453002.MR fuse (verify)'})
    s.part('Device', 'D_Schottky', 'D1', 'SS34', 142.24, 190.5, {'2': 'VIN_F', '1': '+VIN'}, angle=180,
           fields={'Footprint': SMA, 'MPN': 'SS34', 'Notes': 'reverse-polarity block, 40 V 3 A'})
    s.part('Device', 'D_TVS', 'D2', 'SMAJ24CA', 157.48, 200.66, {'1': '+VIN', '2': 'GND'}, angle=270,
           fields={'Footprint': SMA, 'MPN': 'SMAJ24CA', 'Notes': '12 V build: SMAJ15CA'})
    s.part('Device', 'C', 'C1', '10uF 50V', 170.18, 200.66, {'1': '+VIN', '2': 'GND'},
           fields={'Footprint': C1206, 'Notes': 'X7R'})
    s.part('Device', 'C', 'C2', '100nF 50V', 180.34, 200.66, {'1': '+VIN', '2': 'GND'}, fields={'Footprint': C0603})
    s.part('Device', 'R', 'R73', '10k', 193.04, 193.04, {'1': '+VIN', '2': 'LED_VIN'},
           fields={'Footprint': R0603, 'Notes': '12 V build: 4.7k'})
    s.part('Device', 'LED', 'D3', 'RED', 193.04, 208.28, {'2': 'LED_VIN', '1': 'GND'}, angle=90,
           fields={'Footprint': LED0603, 'Notes': 'pump supply present'})

    # ================= E: high-level float + relay (x 95-210, y 222-285)
    T('HIGH-LEVEL CUTOFF (hardware only). The float is closed while the water is below the high mark.\n'
      'Float closed -> relay coil powered -> contact feeds RAIL. High water, a cut cable or a shorted cable\n'
      '(F2 trips) drops the relay, and RAIL (pump + / stepstick VM) goes dead. Firmware only reads it (U4).\n'
      'Cable: 2-core shielded pair, shield to J11-3 at this end only.  12 V build: G5LE-1 DC12, R74 2.2k.', 95, 222)
    s.part('Device', 'Polyfuse', 'F2', '100mA hold', 106.68, 248.92, {'1': '+VIN', '2': 'FLOAT_V'}, angle=90,
           fields={'Footprint': 'Fuse:Fuse_1812_4532Metric', 'MPN': 'Bourns MF-MSMF010-2 (0.1 A, 60 V)'})
    s.part('Connector_Generic', 'Conn_01x03', 'J11', 'HIGH FLOAT', 101.6, 271.78,
           {'1': 'FLOAT_V', '2': 'FLOAT_RET', '3': 'GND'},
           fields={'Footprint': MKDS3, 'MPN': 'MKDS 1,5/3-5,08 (1715734)', 'Manufacturer': 'Phoenix Contact'})
    s.part('Relay', 'G5LE-1', 'K1', 'G5LE-1 DC24', 152.4, 261.62,
           {'2': 'FLOAT_RET', '5': 'GND', '1': '+VIN', '3': 'RAIL', '4': 'NC'},
           fields={'Footprint': 'Relay_THT:Relay_SPDT_Omron-G5LE-1', 'MPN': 'G5LE-1 DC24', 'Manufacturer': 'Omron',
                   'Notes': '1 COM, 3 NO, 4 NC (unused), 2/5 coil'})
    s.part('Device', 'D', 'D4', '1N4148W', 129.54, 261.62, {'1': 'FLOAT_RET', '2': 'GND'}, angle=270,
           fields={'Footprint': SOD123, 'Notes': 'coil flyback'})
    s.part('Device', 'R', 'R74', '4.7k', 177.8, 240.03, {'1': 'FLOAT_RET', '2': 'FOK_A'},
           fields={'Footprint': R1206, 'Notes': '0.1 W at 24 V: 1206. 12 V build: 2.2k'})
    s.part('Device', 'LED', 'D5', 'GREEN', 177.8, 255.27, {'2': 'FOK_A', '1': 'FOK_K'}, angle=90,
           fields={'Footprint': LED0603, 'Notes': 'FLOAT OK (relay coil powered)'})
    s.part('Isolator', 'PC817', 'U4', 'PC817', 195.58, 270.51,
           {'1': 'FOK_K', '2': 'GND', '4': 'HIGH_FLOAT_SENSE', '3': 'GND'},
           fields={'Footprint': 'Package_DIP:SMDIP-4_W9.53mm', 'MPN': 'PC817 SMD gull-wing (verify lead span)'})
    s.part('Device', 'R', 'R75', '10k', 195.58, 251.46, {'1': '+3V3', '2': 'HIGH_FLOAT_SENSE'},
           fields={'Footprint': R0603, 'Notes': 'IO5 reads low = float OK'})

    # ================= F: pump B, brushed (x 215-305, y 165-245)
    T('PUMP B (brushed, e.g. the 81 ml/min Kamoer): low-side MOSFET on IO16.\n'
      'Runs only with RAIL live (float OK) AND the gate high. Dead ESP32 -> R77 holds the gate low.\n'
      'Build B: R76 fitted, R79 DNP.  Build A (stepper): R76 DNP (Q1 may be left off), R79 fitted.', 215, 165)
    s.part('Connector_Generic', 'Conn_01x02', 'J12', 'PUMP', 223.52, 193.04, {'1': 'RAIL', '2': 'PUMP_N'},
           fields={'Footprint': MKDS2, 'MPN': 'MKDS 1,5/2-5,08 (1715721)', 'Manufacturer': 'Phoenix Contact',
                   'Notes': '1 = pump +, 2 = pump -'})
    s.part('Device', 'D_Schottky', 'D6', 'SS34', 241.3, 195.58, {'1': 'RAIL', '2': 'PUMP_N'}, angle=270,
           fields={'Footprint': SMA, 'MPN': 'SS34', 'Notes': 'motor flyback'})
    s.part('Device', 'R', 'R78', '10k', 254.0, 187.96, {'1': 'RAIL', '2': 'LED_PMP'},
           fields={'Footprint': R0603, 'Notes': '12 V build: 4.7k'})
    s.part('Device', 'LED', 'D7', 'YELLOW', 254.0, 203.2, {'2': 'LED_PMP', '1': 'PUMP_N'}, angle=90,
           fields={'Footprint': LED0603, 'Notes': 'pump energized'})
    s.part('Device', 'Q_NMOS_GSD', 'Q1', 'IRLML0040', 274.32, 218.44, {'1': 'GATE', '2': 'GND', '3': 'PUMP_N'},
           fields={'Footprint': SOT23, 'MPN': 'IRLML0040TRPBF', 'Manufacturer': 'Infineon',
                   'Notes': '40 V 3.6 A, Rds(on) specified at Vgs 2.5 V'})
    s.part('Device', 'R', 'R76', '100R', 248.92, 218.44, {'1': 'PUMP_EN', '2': 'GATE'}, angle=90,
           fields={'Footprint': R0603, 'Notes': 'build B only'})
    s.part('Device', 'R', 'R77', '10k', 266.7, 233.68, {'1': 'GATE', '2': 'GND'}, fields={'Footprint': R0603})

    # ================= G: pump A, stepper (x 310-405, y 40-200)
    T('PUMP A (stepper, e.g. KPHM100/400-ST): TMC2209 stepstick, standalone.\n'
      'VM = RAIL, so the high float also cuts the driver. VIO = 3V3.\n'
      'EN (IO16) active low; R79 10k pull-up keeps it disabled at boot\n'
      'and when the ESP32 is dead. MS1/MS2 jumpers to 3V3 (open = 1/8).\n'
      'JP4: bridge only for A4988/DRV8825 (RST-SLP). J15 mates the Kamoer\n'
      'XHP-4 lead: 1 RED, 2 YEL (coil B), 3 BRN, 4 ORG (coil A).\n'
      "Don't plug or unplug the motor with RAIL live.", 312, 40)
    s.part('Connector_Generic', 'Conn_01x08', 'J13', 'STEPSTICK L', 325.12, 99.06,
           {'1': 'PUMP_EN', '2': 'MS1', '3': 'MS2', '4': 'NC', '5': 'SS_RST', '6': 'SS_SLP', '7': 'STEP', '8': 'DIR'},
           fields={'Footprint': 'Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical',
                   'Notes': 'EN MS1 MS2 PDN/MS3 RST/- SLP/- STEP DIR'})
    s.part('Connector_Generic', 'Conn_01x08', 'J14', 'STEPSTICK R', 375.92, 99.06,
           {'1': 'RAIL', '2': 'GND', '3': 'M_2B', '4': 'M_2A', '5': 'M_1A', '6': 'M_1B', '7': '+3V3', '8': 'GND'},
           fields={'Footprint': 'Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical',
                   'Notes': 'VM GND 2B 2A 1A 1B VIO GND'})
    s.part('Jumper', 'Jumper_2_Open', 'JP2', 'MS1', 340.36, 127.0, {'1': 'MS1', '2': '+3V3'}, angle=270,
           fields={'Footprint': 'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical'})
    s.part('Jumper', 'Jumper_2_Open', 'JP3', 'MS2', 353.06, 127.0, {'1': 'MS2', '2': '+3V3'}, angle=270,
           fields={'Footprint': 'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical'})
    s.part('Jumper', 'SolderJumper_2_Open', 'JP4', 'RST-SLP', 340.36, 144.78, {'1': 'SS_RST', '2': 'SS_SLP'},
           fields={'Footprint': 'Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm',
                   'Notes': 'A4988/DRV8825 only; leave open for TMC2209'})
    s.part('Device', 'R', 'R79', '10k', 360.68, 147.32, {'1': '+3V3', '2': 'PUMP_EN'}, dnp=True,
           fields={'Footprint': R0603, 'Notes': 'build A only (EN pull-up); DNP in build B'})
    s.part('Device', 'C_Polarized', 'C3', '100uF 35V', 375.92, 147.32, {'1': 'RAIL', '2': 'GND'},
           fields={'Footprint': 'Capacitor_THT:CP_Radial_D6.3mm_P2.50mm', 'Notes': 'stepstick VM bulk, low-ESR'})
    s.part('Device', 'C', 'C4', '100nF 50V', 388.62, 147.32, {'1': 'RAIL', '2': 'GND'}, fields={'Footprint': C0603})
    s.part('Connector_Generic', 'Conn_01x04', 'J15', 'MOTOR', 345.44, 180.34,
           {'1': 'M_2B', '2': 'M_2A', '3': 'M_1A', '4': 'M_1B'},
           fields={'Footprint': 'Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical', 'MPN': 'B4B-XH-A',
                   'Manufacturer': 'JST'})

    # ================= H: test points + holes (x 310-405, y 215-285)
    T('TEST POINTS + MOUNTING', 312, 215)
    tps = [('TP1', '+VIN'), ('TP2', 'RAIL'), ('TP3', 'GATE'), ('TP4', '+5V'), ('TP5', '+3V3'), ('TP6', 'GND'),
           ('TP7', 'SENS_V')]
    for i, (ref, net) in enumerate(tps):
        s.part('Connector', 'TestPoint', ref, net, 317.5 + i * 12.7, 228.6, {'1': net}, fields=TP)
    for i in range(4):
        s.part('Mechanical', 'MountingHole', 'H%d' % (i + 1), 'M3', 322.58 + i * 12.7, 248.92, {},
               fields={'Footprint': 'MountingHole:MountingHole_3.2mm_M3'})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lib', default='/usr/share/kicad/symbols')
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    sheet = Sheet(Lib(args.lib))
    build(sheet)
    path = os.path.join(OUT_DIR, PROJECT + '.kicad_sch')
    sheet.write(path, 'Calyx-Level carrier')
    # intended netlist, for check_netlist.py
    with open(os.path.join(OUT_DIR, 'intended_nets.txt'), 'w') as f:
        for net in sorted(sheet.intended):
            f.write('%s: %s\n' % (net, ' '.join(sorted(sheet.intended[net]))))
    print('wrote', os.path.relpath(path), '-', len(sheet.refs), 'parts,', len(sheet.intended), 'nets')


if __name__ == '__main__':
    main()
