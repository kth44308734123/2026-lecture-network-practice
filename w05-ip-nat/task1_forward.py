#!/usr/bin/env python3
"""Week 5 · Task 1 — Subnets and longest-prefix match.

Textbook §4.3.2 (IPv4 addressing, CIDR) and §4.3.3 (forwarding).

Two things a router does with every packet: work out which prefixes the
destination falls inside, and pick the longest one. The second is the whole
of "longest prefix match", and it is the reason the internet's routing table
can hold a million entries and still be answerable.

You build both, from integers up. No `ipaddress` module - that library is
exactly the thing you are supposed to understand this week.

    python3 task1_forward.py --verify
"""
import argparse


def _mask(plen):
    return (0xFFFFFFFF << (32 - plen)) & 0xFFFFFFFF


def _dotted(ip):
    return ".".join(str((ip >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def _to_int(address):
    ip = 0
    for o in address.split("."):
        ip = (ip << 8) | int(o)
    return ip


def parse_cidr(cidr):
    """'163.152.6.0/24' -> (network as int, prefix length).

    Requirements: reject a prefix length outside 0-32, and reject an address
    whose host bits are set when they should not be (163.152.6.5/24 is a
    common way to write a host, but it is not a network).
    """
    addr, _, plen = cidr.partition("/")
    if not plen.isdigit():
        raise ValueError(f"bad prefix length in {cidr!r}")
    plen = int(plen)
    if not 0 <= plen <= 32:
        raise ValueError(f"prefix length {plen} outside 0-32")
    octets = addr.split(".")
    if len(octets) != 4 or not all(o.isdigit() and 0 <= int(o) <= 255 for o in octets):
        raise ValueError(f"bad address in {cidr!r}")
    ip = 0
    for o in octets:                       # four bytes -> one 32-bit integer
        ip = (ip << 8) | int(o)
    mask = _mask(plen)
    if ip & ~mask & 0xFFFFFFFF:            # any host bit set -> not a network
        raise ValueError(f"{cidr!r} has host bits set")
    return ip, plen


def network_range(cidr):
    """'163.152.6.0/24' -> (first usable, last usable, broadcast) as strings.

    Careful at the edges. /31 and /32 do not have a usable host range in the
    ordinary sense - decide what you return and say so in observation.md.
    """
    net, plen = parse_cidr(cidr)
    size = 1 << (32 - plen)
    last = net + size - 1                  # the broadcast address
    if plen >= 31:
        # /32: one address, no network/broadcast. /31: two addresses, both usable
        # on point-to-point links (RFC 3021). So first = net, last = broadcast.
        return _dotted(net), _dotted(last), _dotted(last)
    return _dotted(net + 1), _dotted(last - 1), _dotted(last)


class ForwardingTable:
    """Longest-prefix-match forwarding.

    add(cidr, next_hop)  ·  lookup(address) -> next_hop or None

    The default route 0.0.0.0/0 matches everything and is the shortest prefix,
    so it must lose to any other match. If two entries have the same prefix
    length, the table is malformed - say what you do.
    """

    def __init__(self):
        self.routes = {}                   # (network, plen) -> next hop

    def add(self, cidr, next_hop):
        # same (network, plen) added twice: the later one replaces the earlier
        self.routes[parse_cidr(cidr)] = next_hop

    def lookup(self, address):
        ip = _to_int(address)
        best = None                        # (plen, next hop)
        for (net, plen), hop in self.routes.items():
            if ip & _mask(plen) == net and (best is None or plen > best[0]):
                best = (plen, hop)
        return best[1] if best else None


# ------------------------------------------------------------------- harness
RANGE_CASES = [
    ("192.168.0.0/24",  "192.168.0.1",   "192.168.0.254",  "192.168.0.255"),
    ("10.0.0.0/8",      "10.0.0.1",      "10.255.255.254", "10.255.255.255"),
    ("172.16.32.0/20",  "172.16.32.1",   "172.16.47.254",  "172.16.47.255"),
    ("203.0.113.64/26", "203.0.113.65",  "203.0.113.126",  "203.0.113.127"),
]

TABLE = [
    ("0.0.0.0/0",       "default-gw"),
    ("10.0.0.0/8",      "campus"),
    ("10.20.0.0/16",    "eng-building"),
    ("10.20.30.0/24",   "lab-floor"),
    ("10.20.30.64/26",  "lab-rack-2"),
    ("192.168.1.0/24",  "home"),
]

LOOKUP_CASES = [
    ("10.20.30.70",   "lab-rack-2"),     # inside all four 10.x entries
    ("10.20.30.10",   "lab-floor"),
    ("10.20.99.1",    "eng-building"),
    ("10.99.0.1",     "campus"),
    ("8.8.8.8",       "default-gw"),
    ("192.168.1.77",  "home"),
]


def verify():
    fails = 0
    for cidr, first, last, bcast in RANGE_CASES:
        try:
            got = network_range(cidr)
        except NotImplementedError:
            print("  network_range is still a stub"); return 1
        except Exception as e:
            print(f"  FAIL  {cidr:<18} raised {e!r}"); fails += 1; continue
        ok = tuple(got) == (first, last, bcast)
        print(f"  {'ok  ' if ok else 'FAIL'}  {cidr:<18} {got}")
        fails += not ok

    t = ForwardingTable()
    try:
        for cidr, hop in TABLE:
            t.add(cidr, hop)
    except NotImplementedError:
        print("  ForwardingTable is still a stub"); return 1

    for addr, expect in LOOKUP_CASES:
        got = t.lookup(addr)
        ok = got == expect
        print(f"  {'ok  ' if ok else 'FAIL'}  {addr:<16} -> {got}  (want {expect})")
        fails += not ok

    print(f"\n  {len(RANGE_CASES) + len(LOOKUP_CASES) - fails}"
          f"/{len(RANGE_CASES) + len(LOOKUP_CASES)} ok")
    return 1 if fails else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    raise SystemExit(verify() if a.verify else p.print_help())
