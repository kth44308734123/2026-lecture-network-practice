#!/usr/bin/env python3
"""Week 4 · Task 1 — Build reliable delivery on top of an unreliable channel.

Textbook §3.4 (reliable data transfer) and §3.5 (TCP's sequence numbers).

`UnreliableChannel` below loses packets, reorders them, duplicates them, and
delays them. It is the network as §3.4 models it. Your job is to move a file
across it and have the bytes arrive intact and in order.

That is the whole of TCP's reliability story with the congestion control taken
out, and it is worth building once by hand before you ever trust a socket again.

    python3 task1_rdt.py --verify
"""
import argparse, hashlib, random

PAYLOAD = 8            # bytes per packet - small, so you see the sequencing


class UnreliableChannel:
    """Loses 10%, duplicates 3%, reorders, and delays. Deterministic by seed.

    You may not make it nicer. You may not read its internals. It is the only
    way your sender can reach your receiver.
    """

    def __init__(self, seed=246, loss=0.10, dup=0.03, reorder=0.10):
        self.rng = random.Random(seed)
        self.loss, self.dup, self.reorder = loss, dup, reorder
        self.wire = []          # packets in flight, in no particular order
        self.stats = {"sent": 0, "lost": 0, "duplicated": 0, "delivered": 0}

    def send(self, packet):
        """Hand a packet to the network. It may never come out."""
        self.stats["sent"] += 1
        if self.rng.random() < self.loss:
            self.stats["lost"] += 1
            return
        copies = 2 if self.rng.random() < self.dup else 1
        self.stats["duplicated"] += copies - 1
        for _ in range(copies):
            if self.rng.random() < self.reorder and self.wire:
                self.wire.insert(self.rng.randrange(len(self.wire)), packet)
            else:
                self.wire.append(packet)

    def receive(self):
        """Take the next packet out, or None if the network has nothing."""
        if not self.wire:
            return None
        self.stats["delivered"] += 1
        return self.wire.pop(0)


class Sender:
    """Selective-repeat sliding window.

    Stop-and-wait would be simpler, but with 10% loss on *both* directions it
    spends most steps idle. The window keeps WINDOW packets in flight, and each
    packet has its own retransmit timer, so one loss never stalls the others.

    The ACK carries the sequence number it acknowledges. Matching that number
    against what we actually sent is what makes duplicate and stale ACKs
    harmless: an ACK for something already acknowledged changes nothing.
    """
    WINDOW = 8
    RTO = 25            # steps to wait before assuming a packet is lost

    def __init__(self, data_channel, ack_channel, data):
        self.up, self.down = data_channel, ack_channel
        self.chunks = [data[i:i + PAYLOAD] for i in range(0, len(data), PAYLOAD)]
        self.acked = set()
        self.sent_at = {}           # seq -> step of last (re)transmission
        self.base = 0               # lowest unacknowledged seq
        self.now = 0

    def step(self):
        self.now += 1
        pkt = self.down.receive()
        if pkt is not None and pkt[0] == "A" and 0 <= pkt[1] < len(self.chunks):
            self.acked.add(pkt[1])
            while self.base in self.acked:
                self.base += 1
        if self.base >= len(self.chunks):
            return False
        # send at most one packet per step: the first unacked seq in the window
        # that was never sent or whose timer ran out
        top = min(self.base + self.WINDOW, len(self.chunks))
        for seq in range(self.base, top):
            if seq in self.acked:
                continue
            if seq not in self.sent_at or self.now - self.sent_at[seq] >= self.RTO:
                self.sent_at[seq] = self.now
                self.up.send(("D", seq, self.chunks[seq]))
                break
        return True


class Receiver:
    """Buffers out-of-order packets, delivers the contiguous prefix."""

    def __init__(self, data_channel, ack_channel):
        self.up, self.down = data_channel, ack_channel
        self.buf = {}               # seq -> payload (dict makes duplicates idempotent)
        self.next = 0               # next seq needed for in-order delivery
        self.out = bytearray()

    def step(self):
        pkt = self.up.receive()
        if pkt is None or pkt[0] != "D":
            return
        _, seq, payload = pkt
        if seq >= self.next:
            self.buf.setdefault(seq, payload)
        while self.next in self.buf:
            self.out += self.buf.pop(self.next)
            self.next += 1
        # always ACK, even a duplicate: the previous ACK may have been the one lost
        self.down.send(("A", seq))

    def data(self):
        """The bytes reassembled so far."""
        return bytes(self.out)


# ------------------------------------------------------------------- harness
def verify(seed=246, size=2000, max_steps=200_000):
    original = bytes(random.Random(seed).getrandbits(8) for _ in range(size))
    up, down = UnreliableChannel(seed), UnreliableChannel(seed + 1)

    # Data goes out over `up`, ACKs come back over `down`. Both are unreliable.
    sender = Sender(up, down, original)
    receiver = Receiver(up, down)

    for _ in range(max_steps):
        alive = sender.step()
        receiver.step()
        if not alive and len(receiver.data() or b"") >= size:
            break

    got = receiver.data() or b""
    ok = hashlib.sha256(got).hexdigest() == hashlib.sha256(original).hexdigest()
    print(f"  bytes    sent {size}   received {len(got)}")
    print(f"  channel  {up.stats}")
    print(f"  result   {'IDENTICAL' if ok else 'CORRUPTED OR INCOMPLETE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    p.add_argument("--seed", type=int, default=246)
    a = p.parse_args()
    raise SystemExit(verify(a.seed) if a.verify else p.print_help())
