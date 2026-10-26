#!/usr/bin/env python3
"""Check the schematic's real connectivity against what the generator intended.

    kicad-cli sch export netlist --format kicadsexpr -o /tmp/cl.net \\
        hardware/calyx-level-carrier/calyx-level-carrier.kicad_sch
    python3 hardware/tools/check_netlist.py /tmp/cl.net

KiCad decides connectivity from where wires, labels and pins actually land, so
this catches anything the generator placed wrong: a stub that misses its pin,
two labels that merge nets, a pin left floating. Exit code 1 on any mismatch.

Also flags nets with a single connection (usually a typo in a net name) and
pins that KiCad left unconnected.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_netlist(path):
    txt = open(path).read()
    nets = {}
    for m in re.finditer(r'\(net \(code "?\d+"?\) \(name "([^"]*)"\)(.*?)\)\s*(?=\(net |\)\s*\)\s*$)', txt, re.S):
        name = m.group(1).lstrip('/')
        nodes = set('%s.%s' % (r, p) for r, p in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2)))
        nets[name] = nodes
    return nets


def main():
    netfile = sys.argv[1] if len(sys.argv) > 1 else '/tmp/cl.net'
    intended = {}
    for line in open(os.path.join(HERE, '..', 'calyx-level-carrier', 'intended_nets.txt')):
        net, nodes = line.rstrip('\n').split(': ', 1)
        intended[net] = set(nodes.split())
    actual = parse_netlist(netfile)

    # match each intended net to the actual net that holds its first node
    where = {}
    for name, nodes in actual.items():
        for n in nodes:
            where[n] = name
    errors = 0
    seen_actual = set()
    for net, nodes in sorted(intended.items()):
        homes = {where.get(n, '<unconnected>') for n in nodes}
        if len(homes) != 1:
            print('SPLIT  %-12s intended %s landed in %s' % (net, sorted(nodes), sorted(homes)))
            errors += 1
            continue
        home = homes.pop()
        if home == '<unconnected>':
            print('FLOAT  %-12s %s' % (net, sorted(nodes)))
            errors += 1
            continue
        extra = actual[home] - nodes
        if extra:
            print('MERGE  %-12s also holds %s (KiCad net %s)' % (net, sorted(extra), home))
            errors += 1
        seen_actual.add(home)
        if len(nodes) < 2 and not net.startswith('V12'):
            print('NOTE   %-12s has one connection: %s' % (net, sorted(nodes)))
    for name, nodes in actual.items():
        if name not in seen_actual and not name.startswith('unconnected-'):
            print('STRAY  KiCad net %s %s' % (name, sorted(nodes)))
            errors += 1
    print('%d intended nets, %d KiCad nets, %d problem(s)' % (len(intended), len(actual), errors))
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
