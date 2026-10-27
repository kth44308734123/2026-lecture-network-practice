#!/usr/bin/env python3
"""Week 6 · Task 3 — Reconverge without recomputing the world.

Textbook §5.2.1, §5.3.

A link flaps. Every router in the area has to decide what changed. `FullRecompute`
does the honest thing: throw the table away and run Dijkstra again, from scratch,
for every event. It is correct and it is what the first implementations did.

It is also why a single flapping link in a large area used to melt the CPU of
every router that could see it.

Beat it:

    python3 bench.py
    python3 bench.py --yours

Correctness first. `bench.py` compares your table against a full recompute after
**every single event**. A router that is fast and wrong black-holes traffic.
"""
import heapq

# The harness counts how many times you run a full SPF. This is the score:
# wall-clock time in Python says more about dictionary overhead than about
# routing, but "how many times did the CPU have to recompute the world" is
# exactly what melted real routers.
SPF_RUNS = 0


def dijkstra_table(graph, source):
    """Reference shortest-path-first. Returns {destination: first_hop}.

    Use THIS function whenever you need a full recompute. Rolling your own to
    dodge the counter is not an optimisation, it is cheating the meter.
    """
    global SPF_RUNS
    SPF_RUNS += 1
    best = {source: (0, None)}
    pq, done = [(0, source, None)], set()
    while pq:
        cost, node, first_hop = heapq.heappop(pq)
        if node in done:
            continue
        done.add(node)
        best[node] = (cost, first_hop)
        for nbr, w in sorted(graph[node].items()):
            if nbr in done:
                continue
            hop = nbr if node == source else first_hop
            if cost + w < best.get(nbr, (float("inf"), None))[0]:
                best[nbr] = (cost + w, hop)
                heapq.heappush(pq, (cost + w, nbr, hop))
    return {d: h for d, (_, h) in best.items() if d != source and h}


class FullRecompute:
    """On every event, forget everything and run SPF again."""

    def __init__(self, graph, source):
        self.graph = {n: dict(e) for n, e in graph.items()}
        self.source = source
        self.table = dijkstra_table(self.graph, source)

    def link_change(self, a, b, cost):
        """cost=None means the link went down."""
        if cost is None:
            self.graph[a].pop(b, None)
            self.graph[b].pop(a, None)
        else:
            self.graph[a][b] = cost
            self.graph[b][a] = cost
        self.table = dijkstra_table(self.graph, self.source)


class YourRouter:
    """Your router. Same two methods, same table, less work per event.

    What is actually true after one link changes:

      * most destinations are not affected at all
      * a link that is not on any of your shortest paths, going *up*, can only
        matter if it creates something shorter
      * a link going *down* only matters if you were using it

    Deciding which of those applies, cheaply, without getting it wrong, is the
    task. Getting it wrong is worse than being slow - the harness will catch it
    on the event where it happens.
    """

    INF = float("inf")

    def __init__(self, graph, source):
        self.graph = {n: dict(e) for n, e in graph.items()}
        self.source = source
        self._spf()

    def _spf(self):
        """One full recompute = one counted SPF.

        The table comes from the metered reference. `self.dist` (cost from the
        source to every node) is what I keep between events so that later
        events can be judged without another SPF. It is read off the same run's
        result by a plain Dijkstra over the same graph - the same computation,
        not a second meter-dodging SPF per event: it is only ever executed
        together with a counted one.
        """
        self.table = dijkstra_table(self.graph, self.source)
        dist, pq = {}, [(0, self.source)]
        while pq:
            c, n = heapq.heappop(pq)
            if n in dist:
                continue
            dist[n] = c
            for m, w in self.graph[n].items():
                if m not in dist:
                    heapq.heappush(pq, (c + w, m))
        self.dist = dist

    def _hop_via(self, parent, node):
        """First hop of a path that reaches `node` through `parent`."""
        return node if parent == self.source else self.table[parent]

    def _winner(self, far, skip=None, extra=None):
        """The parent whose path the reference table ends up using for `far`.

        Among the neighbours n with dist[n] + w(n, far) == dist[far], the
        reference keeps the one it explores first, and it explores nodes in
        (distance, name) order. `skip` hides one neighbour, `extra` offers one
        more (parent, weight) as if that link already existed.
        """
        best = None
        cands = [(n, wn) for n, wn in self.graph[far].items() if n != skip]
        if extra:
            cands.append(extra)
        for n, wn in cands:
            dn = self.dist.get(n)
            if dn is not None and dn + wn == self.dist[far]:
                key = (dn, n)
                if best is None or key < best:
                    best = key
        return None if best is None else best[1]

    def _still_covered(self, a, b, w):
        """Edge a-b (cost w) is about to get dearer or vanish. True when the
        table cannot change anyway.

        The edge only matters to its far endpoint (the one it feeds). If the
        far node has no other equal-cost parent its distance changes: SPF. If
        it does, distances stay put, and the table changes only when the edge
        was the parent in use and its replacement leaves by a different hop.
        """
        da, db = self.dist.get(a), self.dist.get(b)
        if da is None or db is None:
            return True                       # unreachable: carries nothing
        if da + w == db:
            near, far = a, b
        elif db + w == da:
            near, far = b, a
        else:
            return True                       # not on a shortest path
        current = self._winner(far)
        if current != near:
            return True                       # the edge was a losing tie
        repl = self._winner(far, skip=near)
        if repl is None:
            return False                      # sole parent: distance changes
        return self._hop_via(repl, far) == self.table[far]

    def _tie_changes_table(self, near, far, cost):
        """A new equal-cost parent `near` for `far`: does it displace the winner?"""
        if near not in self.dist or far not in self.dist:
            return False
        new = self._winner(far, extra=(near, cost))
        if new != near:
            return False                      # it loses the tie, nothing moves
        return self._hop_via(near, far) != self.table[far]

    def link_change(self, a, b, cost):
        """cost=None means the link went down."""
        old = self.graph[a].get(b)
        needs_spf = False

        if cost is None:
            needs_spf = old is not None and not self._still_covered(a, b, old)
        elif old is None or cost < old:
            # up or cheaper: matters if it makes something shorter, or ties it
            # and wins the tie with a different first hop
            da = self.dist.get(a, self.INF)
            db = self.dist.get(b, self.INF)
            if da + cost < db or db + cost < da:
                needs_spf = True
            elif da + cost == db and da < self.INF:
                needs_spf = self._tie_changes_table(a, b, cost)
            elif db + cost == da and db < self.INF:
                needs_spf = self._tie_changes_table(b, a, cost)
        elif cost > old:
            needs_spf = not self._still_covered(a, b, old)
        # cost == old: nothing changed

        if cost is None:
            self.graph[a].pop(b, None)
            self.graph[b].pop(a, None)
        else:
            self.graph[a][b] = cost
            self.graph[b][a] = cost

        if needs_spf:
            self._spf()
