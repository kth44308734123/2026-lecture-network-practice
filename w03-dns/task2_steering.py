#!/usr/bin/env python3
"""Week 3 · Task 2 — Does DNS actually steer you? Measure it.

Textbook §2.4.3 (records) and §2.5 (CDNs).

The lecture claims two things:

    (a) most large sites are served by a CDN, reached through a CNAME chain
    (b) DNS steers each user to a *nearby* replica

Both are testable from your laptop, and one of them is harder to prove than
the slide makes it look. Your job is to produce the evidence and a number.

    python3 task2_steering.py --collect        # gather the raw data
    python3 task2_steering.py --report         # your analysis

What you have to build
----------------------
1.  For each hostname in SITES, follow the CNAME chain to its end and record
    every hop. `--collect` should leave the raw data in out/chains.json.

2.  Decide, for each site, whether it is served by a **third party**.
    This is the hard part and there is no single right answer:

      - `www.microsoft.com` ends at `akamaiedge.net`     - clearly third party
      - `www.netflix.com`   stops inside `netflix.com`   - own CDN, not third party
      - some sites have no CNAME at all and still sit behind a CDN (anycast)
      - `foo.cloudfront.net` and `foo.s3.amazonaws.com` are both Amazon,
        but they are not the same service

    Write down the rule you used and **defend it in observation.md**. A rule
    that just compares the last two labels will be wrong on at least one of
    the sites below; find which, and say so.

3.  Ask **two different resolvers** for the same name and compare the
    addresses you get back. If DNS really steers by location, a CDN-hosted
    name should answer differently to resolvers sitting in different places.

        RESOLVERS below has your system resolver and two public ones.

    Report: of N CDN-hosted sites, how many returned a different address set
    from a different resolver? Claim (b) predicts most of them. Check it.

Pass condition
--------------
There is no fixed answer. You pass by producing, in out/report.md:

  - the table: site | chain length | final zone | third party? | your rule's verdict
  - the steering number: "X of N sites answered differently to a different resolver"
  - at least one site where your classification rule was wrong, and why
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

SITES = [
    "www.microsoft.com",     # Akamai, multi-hop
    "www.netflix.com",       # own CDN
    "www.adobe.com",
    "www.cnn.com",
    "www.apple.com",
    "www.korea.ac.kr",       # no CDN at all
    "www.stanford.edu",
    "www.bbc.co.uk",
    "www.spotify.com",
    "www.github.com",
    "www.wikipedia.org",
    "www.nytimes.com",
]

RESOLVERS = {
    "system": None,          # whatever is in your resolv.conf
    "google": "8.8.8.8",
    "quad9":  "9.9.9.9",
    # 이 노트북의 시스템 리졸버가 이미 8.8.8.8 이라 'system' 과 'google' 이
    # 같은 관측이 되어버린다. 관측 지점을 실제로 하나 더 얻으려고 국내 ISP
    # 리졸버를 추가했다 (path (B) 가 말하는 "거리가 다른 두 리졸버").
    "kt":     "168.126.63.1",
}


def dig(name, rtype="A", server=None):
    """Raw lookup. Transport only - the thinking is yours."""
    args = ["dig", "+short", name, rtype]
    if server:
        args.insert(1, f"@{server}")
    out = subprocess.run(args, capture_output=True, text=True).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


# ------------------------------------------------------------------ 분류 규칙
# eTLD+1(등록 가능 도메인)을 뽑기 위한 최소 public suffix 목록.
# "마지막 두 라벨"만 보면 www.bbc.co.uk 의 소유자가 'co.uk' 가 되어버린다.
PUBLIC_SUFFIXES = {
    "co.uk", "org.uk", "gov.uk", "ac.uk",
    "ac.kr", "co.kr", "or.kr", "go.kr", "ne.kr",
    "co.jp", "ne.jp", "or.jp",
    "com.au", "com.br", "com.cn", "co.in", "com.mx",
}

# 같은 회사가 여러 도메인으로 자기 인프라를 굴리는 경우.
# "도메인이 다르다 = 남의 CDN 이다" 라는 순진한 결론을 막는 예외 목록이고,
# 이 목록이 필요하다는 사실 자체가 규칙의 한계를 보여준다.
SAME_OPERATOR = [
    {"wikipedia.org", "wikimedia.org"},        # 같은 재단이 직접 운영
    {"netflix.com", "nflxso.net", "nflxvideo.net", "netflix.net"},
    {"apple.com", "aaplimg.com", "cdn-apple.com"},
    {"microsoft.com", "microsoft.net"},
    {"github.com", "github.io", "githubassets.com"},
]

# 주소의 역방향 조회(PTR)에서 이 이름이 보이면 제3자 CDN 위에 있다는 신호.
# CNAME 이 아예 없는 사이트(애니캐스트)를 잡아내기 위한 보조 증거다.
CDN_OPERATORS = {
    "akamaiedge.net": "Akamai", "akamai.net": "Akamai", "akadns.net": "Akamai",
    "edgekey.net": "Akamai", "edgesuite.net": "Akamai", "akamaitechnologies.com": "Akamai",
    "fastly.net": "Fastly", "fastlylb.net": "Fastly",
    "cloudfront.net": "CloudFront", "amazonaws.com": "AWS",
    "cloudflare.com": "Cloudflare", "cloudflare.net": "Cloudflare",
    "azureedge.net": "Azure CDN", "azurefd.net": "Azure Front Door",
    "llnwd.net": "Limelight", "edgecastcdn.net": "Edgecast",
    "impervadns.net": "Imperva", "cdn77.org": "CDN77",
}


def registrable(name):
    """eTLD+1. www.bbc.co.uk -> bbc.co.uk,  e13678.dscb.akamaiedge.net -> akamaiedge.net"""
    labels = name.rstrip(".").lower().split(".")
    if len(labels) < 2:
        return name
    if ".".join(labels[-2:]) in PUBLIC_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def naive_zone(name):
    """일부러 순진하게: 마지막 두 라벨만 본다. 어디서 틀리는지 보려고 남겨둔다."""
    labels = name.rstrip(".").lower().split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else name


def same_operator(a, b):
    if a == b:
        return True
    return any({a, b} <= group for group in SAME_OPERATOR)


def cdn_of(name):
    """이름이 알려진 CDN 사업자 존 안에 있으면 그 이름을 돌려준다."""
    z = registrable(name)
    return CDN_OPERATORS.get(z)


# ------------------------------------------------------------------- 수집
def cname_chain(name, server=None, max_hops=10):
    """CNAME 사슬을 끝까지 따라간다. B1."""
    chain, cur = [name], name
    while len(chain) <= max_hops:
        targets = [t.rstrip(".") for t in dig(cur, "CNAME", server)
                   if t and not t.startswith(";")]
        if not targets:
            break
        nxt = targets[0].lower()
        if nxt in chain:          # 루프 방지
            break
        chain.append(nxt)
        cur = nxt
    return chain


def system_nameservers():
    """resolv.conf 의 리졸버. 'system' 이 공개 리졸버와 같은지 확인하려고 읽는다."""
    try:
        return [l.split()[1] for l in open("/etc/resolv.conf", encoding="utf-8")
                if l.startswith("nameserver")]
    except OSError:
        return []


def ptr_of(addr):
    out = subprocess.run(["dig", "+short", "-x", addr],
                         capture_output=True, text=True).stdout
    names = [l.strip().rstrip(".") for l in out.splitlines() if l.strip()]
    return names[0] if names else ""


def collect(network):
    """SITES × RESOLVERS 를 측정해 out/chains.json 에 병합한다. B1·B2·B3.

    같은 파일에 여러 네트워크의 결과를 **덧붙인다**. 주장 (b)는 '내가 어디
    있는가'에 대한 주장이라 관측 지점이 하나면 검증 자체가 불가능하다.
    """
    path = os.path.join(OUT, "chains.json")
    data = {}
    if os.path.exists(path):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            data = {}

    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    sys_ns = system_nameservers()
    print(f"  network = {network!r}   system resolver = {', '.join(sys_ns) or '?'}"
          f"   ({stamp})\n")
    if any(ns in (RESOLVERS.get("google"), RESOLVERS.get("quad9")) for ns in sys_ns):
        print("  ! 주의: 시스템 리졸버가 공개 리졸버와 동일합니다. "
              "'system' 과 그 리졸버의 결과는 같은 관측입니다.\n")

    for site in SITES:
        entry = data.setdefault(site, {"runs": {}})
        run = {"at": stamp, "resolvers": {}}

        for label, server in RESOLVERS.items():
            chain = cname_chain(site, server)
            addrs = sorted(a for a in dig(site, "A", server)
                           if a and a[0].isdigit())
            run["resolvers"][label] = {
                "server": server,
                "chain": chain,
                "addrs": addrs,
                "ptr": [ptr_of(a) for a in addrs[:2]],
            }

        run["system_nameserver"] = sys_ns
        # 대조군: 같은 리졸버(system)에게 한 번 더 묻는다.
        # 리졸버가 달라서 답이 다른 것인지, 그냥 물을 때마다 도는 것인지를
        # 가르는 유일한 방법이다. 이게 없으면 스티어링 숫자는 아무 뜻이 없다.
        run["control"] = sorted(a for a in dig(site, "A", RESOLVERS["system"])
                                if a and a[0].isdigit())
        run["churn"] = run["control"] != run["resolvers"]["system"]["addrs"]
        run["system_nameserver"] = sys_ns
        entry["runs"][network] = run
        # 표에 쓸 대표 사슬은 시스템 리졸버 기준
        entry["chain"] = run["resolvers"]["system"]["chain"]
        entry["final"] = entry["chain"][-1]

        sysrun = run["resolvers"]["system"]
        print(f"  {site:<22} hops={len(entry['chain']):<2} "
              f"final={entry['final']:<45} {','.join(sysrun['addrs'][:2])}")

    json.dump(data, open(path, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"\n  -> {path}   ({len(data)} sites, "
          f"networks: {', '.join(sorted({n for s in data.values() for n in s['runs']}))})")


# ------------------------------------------------------------------- 분석
def classify(site, entry):
    """이 사이트는 제3자가 서빙하는가? 규칙은 두 단계다.

    1) 사슬 규칙 - CNAME 사슬의 끝이 **다른 운영자**의 등록 도메인이면 제3자.
       eTLD+1 로 비교하고, 같은 회사가 쓰는 별도 도메인은 예외 목록으로 뺀다.
    2) 사슬이 없을 때(길이 1) - CNAME 만으로는 아무 말도 할 수 없다.
       애니캐스트로 CDN 뒤에 있는 사이트가 여기 숨는다. 그래서 주소의
       역방향 조회(PTR)를 보조 증거로 쓴다.
    """
    chain = entry["chain"]
    final = entry["final"]
    site_zone, final_zone = registrable(site), registrable(final)

    if len(chain) > 1 and not same_operator(site_zone, final_zone):
        return True, f"사슬 끝이 {final_zone} (다른 운영자)", "chain"
    if len(chain) > 1:
        return False, f"사슬이 {final_zone} 안에서 끝남 (자체 CDN)", "chain"

    # CNAME 이 없다 - 주소를 직접 본다
    for run in entry["runs"].values():
        for r in run["resolvers"].values():
            for p in r["ptr"]:
                if p and cdn_of(p):
                    return True, f"CNAME 없음, 그러나 PTR이 {cdn_of(p)} ({registrable(p)})", "ptr"
    return False, "CNAME 없음, PTR도 CDN 아님", "none"


def naive_verdict(site, entry):
    """마지막 두 라벨만 비교하는 규칙. 어디서 틀리는지 보려고 같이 돌린다."""
    return naive_zone(site) != naive_zone(entry["final"])


def steering(entry):
    """리졸버/네트워크마다 다른 주소 집합이 왔는가? B5.

    churn=True 면 **같은 리졸버**도 두 번 물으면 다른 답을 준 사이트다.
    그런 사이트에서 '리졸버마다 답이 다르다'는 것은 스티어링의 증거가 되지
    못한다 - 그냥 매 질의마다 도는 것일 수도 있으니까.
    """
    sets = {}
    for net, run in entry["runs"].items():
        for label, r in run["resolvers"].items():
            sets[f"{net}/{label}"] = tuple(r["addrs"])
        if run.get("control"):
            sets[f"{net}/system(2회차)"] = tuple(run["control"])
    distinct = {v for v in sets.values() if v}
    churn = any(run.get("churn") for run in entry["runs"].values())
    return len(distinct), sets, churn


def report():
    path = os.path.join(OUT, "chains.json")
    if not os.path.exists(path):
        raise SystemExit("out/chains.json 이 없습니다. 먼저 --collect 를 돌리세요.")
    data = json.load(open(path, encoding="utf-8"))
    networks = sorted({n for s in data.values() for n in s["runs"]})

    rows, disagree, third_party = [], [], []
    for site in SITES:
        entry = data.get(site)
        if not entry:
            continue
        verdict, why, basis = classify(site, entry)
        naive = naive_verdict(site, entry)
        n_sets, sets, churn = steering(entry)
        rows.append((site, entry, verdict, why, basis, naive, n_sets, sets, churn))
        if verdict != naive:
            disagree.append((site, verdict, naive, why))
        if verdict:
            third_party.append(site)

    steered = [r[0] for r in rows if r[2] and r[6] > 1]
    churny = [r[0] for r in rows if r[8]]
    solid = [r[0] for r in rows if r[2] and r[6] > 1 and not r[8]]

    L = []
    A = L.append
    A("# Week 3 · Task 2 — CNAME chains and DNS steering\n")
    A(f"측정: {len(SITES)} sites × {len(RESOLVERS)} resolvers "
      f"× {len(networks)} networks ({', '.join(networks)})\n")

    A("\n## 표 · 사슬과 판정\n")
    A("| site | chain length | final zone | third party? | naive rule | 근거 |")
    A("|---|---|---|---|---|---|")
    for site, entry, verdict, why, basis, naive, n_sets, sets, churn in rows:
        A(f"| `{site}` | {len(entry['chain'])} | `{registrable(entry['final'])}` | "
          f"{'예' if verdict else '아니오'} | {'예' if naive else '아니오'}"
          f"{' ⚠︎' if naive != verdict else ''} | {why} |")

    A("\n## 사슬 전체\n")
    for site, entry, *_ in rows:
        A(f"- `{site}`: " + " → ".join(f"`{h}`" for h in entry["chain"]))

    A("\n## 스티어링 (B5)\n")
    A(f"- 제3자 CDN 으로 판정한 사이트: **{len(third_party)}개** "
      f"({', '.join(third_party) or '없음'})")
    A(f"- 그중 리졸버/네트워크에 따라 **다른 주소 집합**이 온 사이트: "
      f"**{len(steered)}개** ({', '.join(steered) or '없음'})")
    A(f"- 즉: **{len(steered)} of {len(third_party)} sites answered differently "
      f"to a different resolver or network.**")
    A(f"- 다만 그중 **{len(churny)}개**는 같은 리졸버에게 두 번 물어도 답이 달랐다 "
      f"({', '.join(churny) or '없음'}). 이런 사이트는 리졸버 차이가 아니라 "
      f"질의마다 도는 것일 수 있어 스티어링의 증거로 쓸 수 없다.")
    A(f"- 변동을 걷어내고 남는, **리졸버 차이로만 설명되는** 사이트: "
      f"**{len(solid)}개** ({', '.join(solid) or '없음'})")
    A(f"- 관측 지점: {', '.join(networks)}"
      + ("  ← 네트워크가 하나뿐이라 주장 (b)는 절반만 검증됨" if len(networks) < 2 else ""))

    A("\n### 사이트별 응답 집합\n")
    for site, entry, verdict, why, basis, naive, n_sets, sets, churn in rows:
        A(f"\n**`{site}`**"
          + ("  ⚠︎ 같은 리졸버도 두 번 물으면 답이 달랐다 (per-query 변동)" if churn else "")
          + f" — 서로 다른 주소 집합 {n_sets}개")
        for k, v in sets.items():
            A(f"  - `{k}`: {', '.join(v) if v else '(응답 없음)'}")

    A("\n## 규칙이 틀린 곳\n")
    if disagree:
        for site, verdict, naive, why in disagree:
            A(f"- `{site}` — 순진한 규칙(마지막 두 라벨)은 "
              f"**{'제3자' if naive else '자체'}**라고 했지만 실제로는 "
              f"**{'제3자' if verdict else '자체'}**다. {why}")
    else:
        A("- 두 규칙이 이번 측정에서는 갈리지 않았다.")
    A("\n자세한 해석은 `observation.md`.")

    text = "\n".join(L) + "\n"
    out = os.path.join(OUT, "report.md")
    open(out, "w", encoding="utf-8").write(text)
    print(text)
    print(f"  -> {out}")



# ------------------------------------------------------- Part A · 캡처 읽기
# tshark 없이도 out/dns.pcapng 를 직접 읽는다. 목적은 A2·A3·A4 -
# 질의와 응답을 transaction ID 로 짝지어 보고, 위임 응답과 정답 응답이
# '같은 패킷 형식의 다른 섹션'일 뿐이라는 것을 숫자로 확인하는 것.

def _u16(b, i): return (b[i] << 8) | b[i + 1]


def read_packets(path):
    """pcapng 와 고전 pcap 을 둘 다 읽어 (linktype, 패킷 바이트열) 를 내놓는다."""
    raw = open(path, "rb").read()
    magic = raw[:4]

    if magic == b"\x0a\x0d\x0d\x0a":                       # pcapng
        endian, off, linktype = "<", 0, 1
        while off + 12 <= len(raw):
            btype = int.from_bytes(raw[off:off + 4], "little")
            if btype == 0x0A0D0D0A:                        # Section Header Block
                endian = "<" if raw[off + 8:off + 12] == b"\x4d\x3c\x2b\x1a" else ">"
            blen = int.from_bytes(raw[off + 4:off + 8],
                                  "little" if endian == "<" else "big")
            if blen < 12 or off + blen > len(raw):
                break
            body = raw[off + 8:off + blen - 4]
            if btype == 0x00000001:                        # Interface Description
                linktype = int.from_bytes(body[0:2],
                                          "little" if endian == "<" else "big")
            elif btype == 0x00000006:                      # Enhanced Packet Block
                caplen = int.from_bytes(body[12:16],
                                        "little" if endian == "<" else "big")
                yield linktype, body[20:20 + caplen]
            off += blen
        return

    if magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):   # classic pcap
        endian = "little" if magic == b"\xd4\xc3\xb2\xa1" else "big"
        linktype = int.from_bytes(raw[20:24], endian)
        off = 24
        while off + 16 <= len(raw):
            caplen = int.from_bytes(raw[off + 8:off + 12], endian)
            yield linktype, raw[off + 16:off + 16 + caplen]
            off += 16 + caplen
        return

    raise SystemExit(f"{path}: pcap/pcapng 파일이 아닙니다")


def dns_of(linktype, pkt):
    """링크 계층 -> IP -> UDP 를 벗겨 DNS 메시지를 꺼낸다. 아니면 None."""
    if linktype == 1:                       # Ethernet
        if len(pkt) < 14:
            return None
        etype, off = _u16(pkt, 12), 14
        while etype in (0x8100, 0x88A8):    # VLAN 태그
            etype, off = _u16(pkt, off + 2), off + 4
    elif linktype == 0:                     # NULL / loopback
        fam = int.from_bytes(pkt[0:4], "little")
        etype, off = {2: 0x0800, 30: 0x86DD, 24: 0x86DD}.get(fam, 0), 4
    elif linktype == 12:                    # RAW IP
        etype, off = (0x0800 if pkt[0] >> 4 == 4 else 0x86DD), 0
    else:
        return None

    if etype == 0x0800:                     # IPv4
        ihl = (pkt[off] & 0x0F) * 4
        proto = pkt[off + 9]
        src = ".".join(str(b) for b in pkt[off + 12:off + 16])
        dst = ".".join(str(b) for b in pkt[off + 16:off + 20])
        off += ihl
    elif etype == 0x86DD:                   # IPv6
        proto = pkt[off + 6]
        src = dst = "(v6)"
        off += 40
    else:
        return None

    if proto != 17 or off + 8 > len(pkt):   # UDP 만
        return None
    sport, dport = _u16(pkt, off), _u16(pkt, off + 2)
    if 53 not in (sport, dport):
        return None
    msg = pkt[off + 8:off + _u16(pkt, off + 4)]
    if len(msg) < 12:
        return None

    flags = _u16(msg, 2)
    qname, i = [], 12
    while i < len(msg) and msg[i]:
        if msg[i] & 0xC0:                   # 압축 포인터
            break
        qname.append(msg[i + 1:i + 1 + msg[i]].decode("ascii", "replace"))
        i += 1 + msg[i]
    return {
        "src": f"{src}:{sport}", "dst": f"{dst}:{dport}",
        "txid": _u16(msg, 0),
        "qr": (flags >> 15) & 1,            # 0 = 질의, 1 = 응답
        "aa": (flags >> 10) & 1,            # 권한 있는 답
        "rcode": flags & 0xF,
        "qd": _u16(msg, 4), "an": _u16(msg, 6),
        "ns": _u16(msg, 8), "ar": _u16(msg, 10),
        "qname": ".".join(qname) or "(?)",
        "bytes": len(msg),                  # DNS 메시지 크기 = A4
    }


def capture(path=None):
    path = path or os.path.join(OUT, "dns.pcapng")
    if not os.path.exists(path):
        raise SystemExit(f"{path} 이 없습니다. Wireshark 로 'port 53' 캡처를 먼저 저장하세요.")

    rows, n = [], 0
    for linktype, pkt in read_packets(path):
        n += 1
        d = dns_of(linktype, pkt)
        if d:
            d["frame"] = n
            rows.append(d)

    queries = [r for r in rows if r["qr"] == 0]
    responses = [r for r in rows if r["qr"] == 1]
    # A3: 위임 = 답 0개 + 권한 섹션에 NS,  정답 = 답 1개 이상
    delegations = [r for r in responses if r["an"] == 0 and r["ns"] > 0]
    answers = [r for r in responses if r["an"] > 0]
    biggest = max(responses, key=lambda r: r["bytes"]) if responses else None
    # A2: transaction ID 로 짝지어진 질의/응답 한 쌍
    pair = None
    for q in queries:
        m = [r for r in responses if r["txid"] == q["txid"] and r["frame"] > q["frame"]]
        if m:
            pair = (q, m[0])
            break

    print(f"\n  {os.path.basename(path)}: 전체 {n} 패킷 중 DNS {len(rows)}개 "
          f"(질의 {len(queries)}, 응답 {len(responses)})\n")
    print(f"  {'frame':>6} {'dir':<4} {'txid':>6} {'an/ns/ar':>10} {'bytes':>6}  name")
    for r in rows[:60]:
        print(f"  {r['frame']:>6} {'Q' if r['qr']==0 else ('A' if r['an'] else 'D'):<4} "
              f"0x{r['txid']:04x} {r['an']:>3}/{r['ns']:>2}/{r['ar']:>2} "
              f"{r['bytes']:>6}  {r['qname']}")
    if len(rows) > 60:
        print(f"  ... 그리고 {len(rows)-60}개 더")

    L = ["\n## Part A · 내 캡처에서 읽은 것\n",
         f"파일 `out/{os.path.basename(path)}` — 전체 {n} 패킷, DNS {len(rows)}개 "
         f"(질의 {len(queries)} · 응답 {len(responses)})\n"]
    if pair:
        q, a = pair
        L.append(f"- **A2 질의/응답 한 쌍** — frame **{q['frame']}** (질의, "
                 f"`{q['qname']}`, {q['src']} → {q['dst']}) 와 frame **{a['frame']}** "
                 f"(응답, {a['src']} → {a['dst']}). 양쪽 transaction ID 가 "
                 f"모두 `0x{q['txid']:04x}` 이고, 이 값이 둘을 묶는 유일한 근거다.")
    if delegations:
        d = delegations[0]
        L.append(f"- **A3 위임 응답** — frame **{d['frame']}** (`{d['qname']}`): "
                 f"ANSWER {d['an']}개, AUTHORITY {d['ns']}개(NS), ADDITIONAL {d['ar']}개. "
                 f"답은 0개인데 '저기 가서 물어봐'가 {d['ns']}개 들어 있다.")
    if answers:
        a = answers[0]
        L.append(f"- **A3 정답 응답** — frame **{a['frame']}** (`{a['qname']}`): "
                 f"ANSWER {a['an']}개, AUTHORITY {a['ns']}개, ADDITIONAL {a['ar']}개, "
                 f"aa={a['aa']}. 패킷 형식은 위와 **완전히 같고**, 채워진 섹션만 다르다.")
    if biggest:
        L.append(f"- **A4 가장 큰 응답** — frame **{biggest['frame']}** "
                 f"(`{biggest['qname']}`), DNS 메시지 **{biggest['bytes']} 바이트**. "
                 f"레코드 {biggest['an']}+{biggest['ns']}+{biggest['ar']}개가 들어 있어서 "
                 f"커졌다 (특히 ADDITIONAL 의 glue {biggest['ar']}개).")
    text = "\n".join(L) + "\n"

    rep = os.path.join(OUT, "report.md")
    if os.path.exists(rep):
        old = open(rep, encoding="utf-8").read()
        old = old.split("\n## Part A · 내 캡처에서 읽은 것")[0]
        open(rep, "w", encoding="utf-8").write(old + text)
        print(f"\n  -> {rep} 에 Part A 절을 갱신했습니다")
    print(text)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--collect", action="store_true")
    p.add_argument("--report", action="store_true")
    p.add_argument("--capture", nargs="?", const="", metavar="PCAP",
                   help="out/dns.pcapng 를 읽어 Part A (A2·A3·A4) 를 채운다")
    p.add_argument("--network", default="network-1",
                   help="이 측정을 어느 네트워크에서 했는지 (예: campus-wifi, tethering)")
    a = p.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.collect:
        collect(a.network)
    elif a.report:
        report()
    elif a.capture is not None:
        capture(a.capture or None)
    else:
        p.print_help()
