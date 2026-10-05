#!/usr/bin/env python3
"""Week 3 · Task 3 — Beat the baseline cache.

Textbook §2.4.2 (caching) and §2.4.3 (TTL).

`BaselineCache` below works. It is also bad, in more than one way, and one of
its problems is worse than being slow. Find them, write `YourCache`, and prove
the improvement with the harness:

    python3 bench.py                 # baseline only
    python3 bench.py --yours         # baseline vs. yours, side by side

Rules
-----
* Do not change `bench.py`. If you need to change it to win, you are not
  winning. Say so in observation.md instead.
* `YourCache` must expose the same two methods as `BaselineCache`.
* Speed is not the only score. The harness also counts **stale answers** -
  times you served a record whose TTL had already run out. A cache that keeps
  everything forever is very fast and completely wrong.

Targets
-------
The baseline scores **325 upstream queries, 67.5% hit rate, 266 stale answers**.

  pass  : zero stale answers
  good  : zero stale, and no more upstream queries than the baseline
  strong: the above, plus you can say in observation.md **how few upstream
          queries a correct cache could possibly make on this workload, and
          why you cannot go below that number**

That last one is the real question. Read it before you start optimising -
it will tell you where to stop.
"""
import time


class BaselineCache:
    """A DNS cache that somebody wrote in a hurry.

    It caches. It is not correct, and it is not fast. Both are your problem.
    """

    FIXED_LIFETIME = 60          # seconds we keep anything, regardless of TTL

    def __init__(self, upstream):
        self.upstream = upstream  # upstream(name) -> (address, ttl)
        self.entries = []         # list of [name, address, stored_at]

    def lookup(self, name, now):
        """Return an address for `name`, asking upstream only if we have to."""
        for entry in self.entries:                      # linear scan
            if entry[0] == name:
                if now - entry[2] < self.FIXED_LIFETIME:
                    return entry[1]
                self.entries.remove(entry)
                break
        address, ttl = self.upstream(name)
        self.entries.append([name, address, now])
        return address

    def stats(self):
        return {"entries": len(self.entries)}


class YourCache:
    """TTL 을 지키는 캐시.

    베이스라인의 문제는 두 개처럼 보이지만 뿌리는 하나다 - **TTL 을 버린 것**.
    `FIXED_LIFETIME = 60` 으로 모든 레코드를 60초 보관하면:

      * TTL 이 60초보다 짧은 이름 (microsoft 20초, cnn 30초)
        -> 이미 죽은 레코드를 계속 내놓는다.  **정확성 문제**
      * TTL 이 60초보다 긴 이름 (korea.ac.kr 3600초, dns.google 86400초)
        -> 아직 멀쩡한 레코드를 버리고 다시 물으러 간다.  **성능 문제**

    고치는 방법은 하나뿐이다: 권한 있는 서버가 알려준 TTL 을 **그대로** 쓰고,
    만료 시각을 기록해 두고, 만료 전에는 쓰고 만료되면 버린다.

    (부수적으로 베이스라인의 리스트 선형 탐색도 dict 로 바꿨다. 이름 10개
    짜리 이 워크로드에서는 사실상 공짜지만, 캐시가 수만 개가 되면 O(n) 이
    그대로 비용이 된다. 다만 이건 위 두 문제와 뿌리가 다른 별개의 결함이다.)
    """

    def __init__(self, upstream):
        self.upstream = upstream
        self.entries = {}          # name -> (address, expires_at)
        self.hits = 0
        self.misses = 0
        self.expired = 0           # 만료돼서 버린 횟수

    def lookup(self, name, now):
        hit = self.entries.get(name)
        if hit is not None:
            address, expires_at = hit
            if now < expires_at:           # 아직 살아 있다
                self.hits += 1
                return address
            del self.entries[name]         # 죽었다 - 내놓지 않고 버린다
            self.expired += 1

        address, ttl = self.upstream(name)
        self.entries[name] = (address, now + ttl)
        self.misses += 1
        return address

    def stats(self):
        return {"entries": len(self.entries), "hits": self.hits,
                "misses": self.misses, "expired": self.expired}


# --------------------------------------------------------------- R5 · 바닥
def floor():
    """이 워크로드에서 '올바른' 캐시가 낼 수 있는 최소 upstream 질의 수.

    올바른 캐시는 TTL 이 지난 레코드를 내놓을 수 없다. 그러니 시각 t 의 질의를
    캐시에서 답하려면, 같은 이름에 대해 구간 (t-ttl, t] 안에 upstream 질의가
    한 번은 있었어야 한다. 즉 캐시가 할 수 있는 선택은 '언제 다시 물을까'뿐이고,
    한 번 물으면 딱 ttl 초를 덮는다 - 그 이상은 어떤 자료구조로도 못 늘린다.

    이름별로 보면 이건 '구간 덮기' 문제다. 질의 시각들을 길이 ttl 인 구간으로
    덮되 구간의 시작은 반드시 '아직 안 덮인 첫 질의 시각'이어야 한다(그 질의를
    답하려면 바로 그 때 물어야 하니까). 그래서 욕심쟁이 방식이 곧 최적이고,
    "만료됐을 때만 다시 묻는다"는 YourCache 가 이미 그 바닥에 붙어 있다.

    바닥을 더 낮추려면 TTL 을 어기거나(= 틀린 답), 아무도 묻지 않은 이름을
    미리 당겨오거나(= upstream 질의가 늘어남) 해야 한다. 둘 다 규칙 위반이다.
    """
    from bench import workload, FIXTURE          # 하네스는 읽기만 한다

    per_name, total = {}, 0
    for t, name in workload():
        ttl = FIXTURE[name][1]
        if t >= per_name.get(name, float("-inf")):
            per_name[name] = t + ttl             # 여기서 한 번 물어야만 한다
            total += 1
    return total


if __name__ == "__main__":
    from bench import FIXTURE, workload
    n = floor()
    print(f"\n  이 워크로드에서 올바른 캐시의 바닥 = upstream {n} 회")
    counts = {}
    for _, name in workload():
        counts[name] = counts.get(name, 0) + 1
    print(f"\n  {'name':<22}{'ttl':>7}{'queries':>9}{'수명 최소 질의':>16}")
    for name, (_, ttl) in FIXTURE.items():
        seen, fetches = float("-inf"), 0
        for t, nm in workload():
            if nm == name and t >= seen:
                seen, fetches = t + ttl, fetches + 1
        print(f"  {name:<22}{ttl:>7}{counts.get(name,0):>9}{fetches:>16}")
    print()
