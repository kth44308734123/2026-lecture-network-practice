#!/usr/bin/env python3
"""Week 3 · Task 1 — Build your own iterative resolver.

Textbook §2.4.2 - §2.4.3.

`dig +trace` walks root -> TLD -> authoritative for you. In this task you do
that walk yourself: start at a root server, read the delegation it returns,
ask the next server, and keep going until somebody answers authoritatively.

You may shell out to `dig` for the transport, or use a DNS library
(`dnspython` is in the container). Either is fine - what matters is that
*you* follow the delegations rather than letting a tool do it.

    python3 task1_resolve.py www.korea.ac.kr
    python3 task1_resolve.py --verify        # check yourself against dig

Pass condition
--------------
`--verify` resolves five names with your resolver and with `dig`, and the
addresses must agree. A name behind a CDN may legitimately return a different
address each time; the harness compares the *set of authoritative nameservers*
you ended at for those, not the address.
"""
import argparse, subprocess, sys

# Root servers. Everything starts here; there is no earlier step.
ROOT_SERVERS = [
    "198.41.0.4",       # a.root-servers.net
    "199.9.14.201",     # b.root-servers.net
    "192.33.4.12",      # c.root-servers.net
]

# (name, kind).  "stable" names must match dig exactly.  "cdn" names are served
# from many replicas and may legitimately give you a different address than dig
# got a second earlier - for those we only require that you reached an answer.
VERIFY_NAMES = [
    ("www.korea.ac.kr", "stable"),
    ("dns.google", "stable"),
    ("en.wikipedia.org", "stable"),
    ("www.stanford.edu", "stable"),
    ("www.microsoft.com", "cdn"),
]



class ResolveError(Exception):
    """이 이름은 못 풀었다 - 위임이 끊겼거나, 아무도 대답을 안 했거나, 깊이 초과."""


class Resolver:
    """직접 걷는 반복적(iterative) 리졸버.

    핵심은 '남에게 대신 찾아달라고 하지 않는다'는 것. 한 서버에게 물으면
    "내 것 아니다, 저쪽에 물어봐" 하고 위임(delegation)을 주고, 그럼 그쪽으로
    간다. 그걸 답이 나올 때까지 반복한다.

        resolve(name) -> (address, path)
            address : 최종적으로 얻은 A 레코드 (문자열)
            path    : 내가 실제로 질의한 서버들의 순서 목록 (풀이 과정 증거)

    가는 길에 반드시 만나는 것들:

    1.  위임은 NS '이름'을 준다. 그 이름의 A 레코드(glue)가 같이 오기도 하고
        안 오기도 한다. glue가 없으면 그 네임서버 이름부터 먼저 풀어야 한다
        - 그게 또 하나의 walk다.  (R3)
    2.  응답 없는 서버. 실패로 끝내지 말고 다음 서버로.  (R4)
    3.  CNAME. 내가 물은 이름이 아니라 다른 이름에 대한 답이 올 수 있고,
        그러면 그 이름으로 처음부터 다시 걸어야 한다.  (R5)
    4.  루프. 깊이를 반드시 제한한다.  (R6)
    """

    MAX_HOPS = 16      # 한 이름을 푸는 동안 위임을 따라갈 수 있는 최대 단계 (R6)
    MAX_DEPTH = 4      # glue 없는 NS를 푸느라 들어가는 재귀 깊이 상한 (R6)
    MAX_CNAME = 8      # CNAME 을 몇 번까지 따라갈지 (R6)

    def __init__(self):
        self.path = []          # 이번 resolve()에서 물어본 서버 전부 (순서대로)
        self.glue_misses = 0    # glue 없는 위임을 만난 횟수
        self.extra_lookups = 0  # 그것 때문에 추가로 돈 walk 횟수
        self.timeouts = 0       # 대답 안 한 서버 수 (R4가 실제로 발동한 횟수)

    # ------------------------------------------------------------- transport
    # dig 를 '전송 수단'으로만 쓴다. 판단은 전부 아래 resolve() 가 한다.
    # +norecurse : 물어본 서버가 나 대신 일해주지 못하게 막는 플래그
    # +comments  : 섹션 머리말(;; ANSWER SECTION: 등)을 남겨서, 같은 형식의
    #              레코드가 '답'으로 온 건지 '위임'으로 온 건지 구분할 수 있게 한다
    def ask(self, server, name, rtype="A"):
        try:
            result = subprocess.run(
                [
                    "dig",
                    f"@{server}",
                    name,
                    rtype,
                    "+norecurse",
                    "+noall",
                    "+comments",
                    "+answer",
                    "+authority",
                    "+additional",
                    "+time=2",
                    "+tries=1",
                ],
                capture_output=True,
                text=True,
                timeout=6,
            )
        except subprocess.TimeoutExpired:
            return None
        return self.parse(result.stdout)

    @staticmethod
    def parse(text):
        """dig 출력 한 덩어리를 {status, aa, answer, authority, additional} 로.

        레코드 한 줄은  이름 TTL 클래스 타입 값  다섯 칸이고, 응답 패킷의
        세 섹션은 전부 '똑같은 형식'이다. 위임과 응답의 차이는 레코드 생김새가
        아니라 '어느 섹션에 들어 있느냐' 뿐이다 - 그래서 섹션을 보고 나눈다.
        """
        out = {"status": None, "aa": False,
               "answer": [], "authority": [], "additional": []}
        section = None
        for line in text.splitlines():
            line = line.rstrip()
            if not line:
                continue
            if line.startswith(";"):
                if "->>HEADER<<-" in line and "status:" in line:
                    out["status"] = line.split("status:")[1].split(",")[0].strip()
                elif line.startswith(";; flags:"):
                    # aa = authoritative answer. 이 서버가 그 존의 주인이라는 뜻
                    out["aa"] = " aa" in line.split(";; flags:")[1].split(";")[0]
                elif "ANSWER SECTION" in line:
                    section = "answer"
                elif "AUTHORITY SECTION" in line:
                    section = "authority"
                elif "ADDITIONAL SECTION" in line:
                    section = "additional"
                elif "SECTION" in line or "PSEUDOSECTION" in line:
                    section = None          # QUESTION / OPT 는 버린다
                continue
            if section is None:
                continue
            parts = line.split()
            if len(parts) < 5 or parts[2] != "IN":
                continue
            out[section].append({
                "name": parts[0].rstrip(".").lower(),
                "ttl": int(parts[1]) if parts[1].isdigit() else 0,
                "type": parts[3],
                "data": parts[4].rstrip(".").lower()
                        if parts[3] in ("NS", "CNAME", "SOA") else parts[4],
            })
        return out

    # ----------------------------------------------------------------- walk
    def resolve(self, name, depth=0):
        """루트에서 시작해 권한 있는 답이 나올 때까지 위임을 따라간다."""
        if depth == 0:                      # 바깥에서 부른 첫 호출이면 기록 초기화
            self.path = []
            self.glue_misses = 0
            self.extra_lookups = 0
            self.timeouts = 0

        if depth > self.MAX_DEPTH:          # R6
            raise ResolveError(f"depth cap hit while resolving {name}")

        qname = name.rstrip(".").lower()
        cname_hops = 0
        servers = list(ROOT_SERVERS)        # R2: 시작은 항상 루트. 그 앞은 없다

        for _ in range(self.MAX_HOPS):      # R6: 무한 위임 루프 차단
            resp = self.query_any(servers, qname)
            if resp is None:
                raise ResolveError(f"no server answered for {qname}")

            # (1) 답이 왔나? 내가 물은 이름의 A 레코드가 ANSWER 섹션에 있으면 끝
            addr = self.pick_a(resp["answer"], qname)
            if addr:
                return addr, self.path

            # (2) CNAME? 답은 왔는데 '다른 이름'에 대한 답이다  (R5)
            target = self.follow_cname(resp["answer"], qname)
            if target and target != qname:
                cname_hops += 1
                if cname_hops > self.MAX_CNAME:     # R6
                    raise ResolveError(f"cname loop at {qname}")
                addr = self.pick_a(resp["answer"], target)
                if addr:                # 운 좋게 같은 응답 안에 A까지 들어있는 경우
                    return addr, self.path
                qname = target          # 아니면 이 이름으로 루트부터 다시
                servers = list(ROOT_SERVERS)
                continue

            # (3) 위임. AUTHORITY 섹션의 NS 이름들이 다음 목적지다
            ns_names = [r["data"] for r in resp["authority"] if r["type"] == "NS"]
            if not ns_names:
                # NS 도 A 도 없다 = 이 존의 주인이 "그런 이름 없다"고 한 것
                raise ResolveError(
                    f"{qname}: no answer and no delegation (status={resp['status']})")

            # glue: 같은 응답의 ADDITIONAL 섹션에 딸려온 NS 의 주소
            glue = {r["name"]: r["data"]
                    for r in resp["additional"] if r["type"] == "A"}
            next_servers = [glue[n] for n in ns_names if n in glue]

            if not next_servers:
                # R3: glue 가 없다. 그럼 네임서버 '이름'부터 따로 풀어야 한다.
                # "재귀적 리졸버"라고 할 때의 재귀가 바로 여기서 나온다.
                self.glue_misses += 1
                for ns in ns_names[:2]:         # 두 개만 시도 - 비용 제한
                    try:
                        self.extra_lookups += 1
                        ns_addr, _ = self.resolve(ns, depth + 1)
                        next_servers.append(ns_addr)
                        break
                    except ResolveError:
                        continue
                if not next_servers:
                    raise ResolveError(f"{qname}: could not resolve any NS of {ns_names}")

            servers = next_servers

        raise ResolveError(f"{qname}: hop cap ({self.MAX_HOPS}) reached")

    # ------------------------------------------------------------- helpers
    def query_any(self, servers, qname):
        """R4: 대답하는 서버가 나올 때까지 후보를 차례로 시도한다."""
        for server in servers:
            self.path.append(server)
            resp = self.ask(server, qname)
            if resp is None or resp["status"] is None:
                self.timeouts += 1              # 응답 없음 -> 다음 서버
                continue
            if resp["status"] in ("SERVFAIL", "REFUSED", "NOTIMP"):
                self.timeouts += 1              # 대답은 했지만 쓸모없음 -> 다음 서버
                continue
            return resp
        return None

    @staticmethod
    def pick_a(records, qname):
        for r in records:
            if r["type"] == "A" and r["name"] == qname:
                return r["data"]
        return None

    @staticmethod
    def follow_cname(records, qname):
        """ANSWER 안의 CNAME 사슬을 끝까지 따라가 최종 이름을 돌려준다."""
        chain = {r["name"]: r["data"] for r in records if r["type"] == "CNAME"}
        cur, seen = qname, set()
        while cur in chain and cur not in seen:
            seen.add(cur)
            cur = chain[cur]
        return cur


# ------------------------------------------------------------------- harness
def dig_answer(name):
    """What the system resolver says, for comparison."""
    out = subprocess.run(["dig", "+short", name, "A"],
                         capture_output=True, text=True).stdout
    return [l for l in out.split() if l and l[0].isdigit()]


def verify():
    r, failures = Resolver(), 0
    for name, kind in VERIFY_NAMES:
        try:
            addr, path = r.resolve(name)
        except NotImplementedError:
            print("Nothing implemented yet - write Resolver.resolve first.")
            return 1
        except Exception as e:
            print(f"  FAIL  {name:<22} your resolver raised {e!r}")
            failures += 1
            continue
        expected = dig_answer(name)
        if addr in expected:
            note = ""
        elif kind == "cdn":
            note = "  <- differs, but this name is CDN-hosted. Explain it."
        else:
            note = "  <- should have matched"
            failures += 1
        print(f"  {'FAIL' if note.endswith('matched') else 'ok  '}  {name:<22} "
              f"you={addr:<16} dig={','.join(expected) or '-'}   "
              f"hops={len(path)}{note}")
    print(f"\n  {len(VERIFY_NAMES) - failures}/{len(VERIFY_NAMES)} ok")
    return 1 if failures else 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", nargs="?", default="www.korea.ac.kr")
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()

    if a.verify:
        sys.exit(verify())

    addr, path = Resolver().resolve(a.name)
    for i, server in enumerate(path, 1):
        print(f"  {i}. asked {server}")
    print(f"\n  {a.name} -> {addr}")


if __name__ == "__main__":
    main()
