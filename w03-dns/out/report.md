# Week 3 · Task 2 — CNAME chains and DNS steering

측정: 12 sites × 4 resolvers × 2 networks (home-wifi, tethering)


## 표 · 사슬과 판정

| site | chain length | final zone | third party? | naive rule | 근거 |
|---|---|---|---|---|---|
| `www.microsoft.com` | 3 | `akamaiedge.net` | 예 | 예 | 사슬 끝이 akamaiedge.net (다른 운영자) |
| `www.netflix.com` | 2 | `netflix.com` | 아니오 | 아니오 | 사슬이 netflix.com 안에서 끝남 (자체 CDN) |
| `www.adobe.com` | 3 | `akamai.net` | 예 | 예 | 사슬 끝이 akamai.net (다른 운영자) |
| `www.cnn.com` | 2 | `fastly.net` | 예 | 예 | 사슬 끝이 fastly.net (다른 운영자) |
| `www.apple.com` | 4 | `akamaiedge.net` | 예 | 예 | 사슬 끝이 akamaiedge.net (다른 운영자) |
| `www.korea.ac.kr` | 1 | `korea.ac.kr` | 아니오 | 아니오 | CNAME 없음, PTR도 CDN 아님 |
| `www.stanford.edu` | 2 | `netlifyglobalcdn.com` | 예 | 예 | 사슬 끝이 netlifyglobalcdn.com (다른 운영자) |
| `www.bbc.co.uk` | 3 | `fastly.net` | 예 | 예 | 사슬 끝이 fastly.net (다른 운영자) |
| `www.spotify.com` | 2 | `fastly.net` | 예 | 예 | 사슬 끝이 fastly.net (다른 운영자) |
| `www.github.com` | 2 | `github.com` | 아니오 | 아니오 | 사슬이 github.com 안에서 끝남 (자체 CDN) |
| `www.wikipedia.org` | 2 | `wikimedia.org` | 아니오 | 예 ⚠︎ | 사슬이 wikimedia.org 안에서 끝남 (자체 CDN) |
| `www.nytimes.com` | 4 | `fastly.net` | 예 | 예 | 사슬 끝이 fastly.net (다른 운영자) |

## 사슬 전체

- `www.microsoft.com`: `www.microsoft.com` → `www.microsoft.com-c-3.edgekey.net` → `e13678.dscb.akamaiedge.net`
- `www.netflix.com`: `www.netflix.com` → `www.prod.ftl.netflix.com`
- `www.adobe.com`: `www.adobe.com` → `www.adobe.com.edgesuite.net` → `a1319.dscr.akamai.net`
- `www.cnn.com`: `www.cnn.com` → `cnn-tls.map.fastly.net`
- `www.apple.com`: `www.apple.com` → `www-apple-com.v.aaplimg.com` → `www.apple.com.edgekey.net` → `e6858.dsce9.akamaiedge.net`
- `www.korea.ac.kr`: `www.korea.ac.kr`
- `www.stanford.edu`: `www.stanford.edu` → `stanford.netlifyglobalcdn.com`
- `www.bbc.co.uk`: `www.bbc.co.uk` → `www.bbc.co.uk.pri.bbc.co.uk` → `bbc.map.fastly.net`
- `www.spotify.com`: `www.spotify.com` → `atc.spotify.map.fastly.net`
- `www.github.com`: `www.github.com` → `github.com`
- `www.wikipedia.org`: `www.wikipedia.org` → `dyna.wikimedia.org`
- `www.nytimes.com`: `www.nytimes.com` → `www.prd.map.nytimes.com` → `www.prd.map.nytimes.xovr.nyt.net` → `nytimes.map.fastly.net`

## 스티어링 (B5)

- 제3자 CDN 으로 판정한 사이트: **8개** (www.microsoft.com, www.adobe.com, www.cnn.com, www.apple.com, www.stanford.edu, www.bbc.co.uk, www.spotify.com, www.nytimes.com)
- 그중 리졸버/네트워크에 따라 **다른 주소 집합**이 온 사이트: **7개** (www.microsoft.com, www.adobe.com, www.cnn.com, www.apple.com, www.bbc.co.uk, www.spotify.com, www.nytimes.com)
- 즉: **7 of 8 sites answered differently to a different resolver or network.**
- 다만 그중 **1개**는 같은 리졸버에게 두 번 물어도 답이 달랐다 (www.apple.com). 이런 사이트는 리졸버 차이가 아니라 질의마다 도는 것일 수 있어 스티어링의 증거로 쓸 수 없다.
- 변동을 걷어내고 남는, **리졸버 차이로만 설명되는** 사이트: **6개** (www.microsoft.com, www.adobe.com, www.cnn.com, www.bbc.co.uk, www.spotify.com, www.nytimes.com)
- 관측 지점: home-wifi, tethering

### 사이트별 응답 집합


**`www.microsoft.com`** — 서로 다른 주소 집합 4개
  - `home-wifi/system`: 104.94.218.45
  - `home-wifi/google`: 104.94.218.45
  - `home-wifi/quad9`: 23.200.181.232
  - `home-wifi/kt`: 104.94.218.45
  - `home-wifi/system(2회차)`: 104.94.218.45
  - `tethering/system`: 23.60.186.45
  - `tethering/google`: 104.94.218.45
  - `tethering/quad9`: 23.63.226.92
  - `tethering/kt`: 23.60.186.45
  - `tethering/system(2회차)`: 23.60.186.45

**`www.netflix.com`** — 서로 다른 주소 집합 1개
  - `home-wifi/system`: 207.45.72.1, 207.45.73.1
  - `home-wifi/google`: 207.45.72.1, 207.45.73.1
  - `home-wifi/quad9`: 207.45.72.1, 207.45.73.1
  - `home-wifi/kt`: 207.45.72.1, 207.45.73.1
  - `home-wifi/system(2회차)`: 207.45.72.1, 207.45.73.1
  - `tethering/system`: 207.45.72.1, 207.45.73.1
  - `tethering/google`: 207.45.72.1, 207.45.73.1
  - `tethering/quad9`: 207.45.72.1, 207.45.73.1
  - `tethering/kt`: 207.45.72.1, 207.45.73.1
  - `tethering/system(2회차)`: 207.45.72.1, 207.45.73.1

**`www.adobe.com`** — 서로 다른 주소 집합 7개
  - `home-wifi/system`: 182.162.106.137, 182.162.106.147
  - `home-wifi/google`: 182.162.106.137, 182.162.106.147
  - `home-wifi/quad9`: 23.208.31.135, 23.208.31.177
  - `home-wifi/kt`: 23.76.153.115, 23.76.153.122
  - `home-wifi/system(2회차)`: 182.162.106.137, 182.162.106.147
  - `tethering/system`: 23.32.56.34, 23.32.56.9
  - `tethering/google`: 23.32.4.146, 23.32.4.168, 23.32.4.178, 23.32.4.187, 23.32.4.209, 23.32.4.210, 23.32.4.218
  - `tethering/quad9`: 23.208.31.135, 23.208.31.169, 23.208.31.177
  - `tethering/kt`: 23.35.218.146, 23.35.218.147
  - `tethering/system(2회차)`: 23.32.56.34, 23.32.56.9

**`www.cnn.com`** — 서로 다른 주소 집합 2개
  - `home-wifi/system`: 151.101.131.5, 151.101.195.5, 151.101.3.5, 151.101.67.5
  - `home-wifi/google`: 151.101.131.5, 151.101.195.5, 151.101.3.5, 151.101.67.5
  - `home-wifi/quad9`: 151.101.131.5, 151.101.195.5, 151.101.3.5, 151.101.67.5
  - `home-wifi/kt`: 146.75.51.5
  - `home-wifi/system(2회차)`: 151.101.131.5, 151.101.195.5, 151.101.3.5, 151.101.67.5
  - `tethering/system`: 146.75.51.5
  - `tethering/google`: 151.101.131.5, 151.101.195.5, 151.101.3.5, 151.101.67.5
  - `tethering/quad9`: 151.101.131.5, 151.101.195.5, 151.101.3.5, 151.101.67.5
  - `tethering/kt`: 146.75.51.5
  - `tethering/system(2회차)`: 146.75.51.5

**`www.apple.com`**  ⚠︎ 같은 리졸버도 두 번 물으면 답이 달랐다 (per-query 변동) — 서로 다른 주소 집합 6개
  - `home-wifi/system`: 23.197.225.61
  - `home-wifi/google`: 23.49.205.28
  - `home-wifi/quad9`: 184.31.228.249
  - `home-wifi/kt`: 104.94.216.37
  - `home-wifi/system(2회차)`: 23.49.205.28
  - `tethering/system`: 23.60.185.29
  - `tethering/google`: 23.60.185.29
  - `tethering/quad9`: 23.210.107.50
  - `tethering/kt`: 23.60.185.29
  - `tethering/system(2회차)`: 23.60.185.29

**`www.korea.ac.kr`** — 서로 다른 주소 집합 1개
  - `home-wifi/system`: 163.152.6.10
  - `home-wifi/google`: 163.152.6.10
  - `home-wifi/quad9`: 163.152.6.10
  - `home-wifi/kt`: 163.152.6.10
  - `home-wifi/system(2회차)`: 163.152.6.10
  - `tethering/system`: 163.152.6.10
  - `tethering/google`: 163.152.6.10
  - `tethering/quad9`: 163.152.6.10
  - `tethering/kt`: 163.152.6.10
  - `tethering/system(2회차)`: 163.152.6.10

**`www.stanford.edu`** — 서로 다른 주소 집합 1개
  - `home-wifi/system`: 15.197.167.90, 3.33.186.135
  - `home-wifi/google`: 15.197.167.90, 3.33.186.135
  - `home-wifi/quad9`: 15.197.167.90, 3.33.186.135
  - `home-wifi/kt`: 15.197.167.90, 3.33.186.135
  - `home-wifi/system(2회차)`: 15.197.167.90, 3.33.186.135
  - `tethering/system`: 15.197.167.90, 3.33.186.135
  - `tethering/google`: 15.197.167.90, 3.33.186.135
  - `tethering/quad9`: 15.197.167.90, 3.33.186.135
  - `tethering/kt`: 15.197.167.90, 3.33.186.135
  - `tethering/system(2회차)`: 15.197.167.90, 3.33.186.135

**`www.bbc.co.uk`** — 서로 다른 주소 집합 2개
  - `home-wifi/system`: 151.101.0.81, 151.101.128.81, 151.101.192.81, 151.101.64.81
  - `home-wifi/google`: 151.101.0.81, 151.101.128.81, 151.101.192.81, 151.101.64.81
  - `home-wifi/quad9`: 151.101.0.81, 151.101.128.81, 151.101.192.81, 151.101.64.81
  - `home-wifi/kt`: 146.75.48.81
  - `home-wifi/system(2회차)`: 151.101.0.81, 151.101.128.81, 151.101.192.81, 151.101.64.81
  - `tethering/system`: 146.75.48.81
  - `tethering/google`: 151.101.0.81, 151.101.128.81, 151.101.192.81, 151.101.64.81
  - `tethering/quad9`: 151.101.0.81, 151.101.128.81, 151.101.192.81, 151.101.64.81
  - `tethering/kt`: 146.75.48.81
  - `tethering/system(2회차)`: 146.75.48.81

**`www.spotify.com`** — 서로 다른 주소 집합 2개
  - `home-wifi/system`: 151.101.131.42, 151.101.195.42, 151.101.3.42, 151.101.67.42
  - `home-wifi/google`: 151.101.131.42, 151.101.195.42, 151.101.3.42, 151.101.67.42
  - `home-wifi/quad9`: 151.101.131.42, 151.101.195.42, 151.101.3.42, 151.101.67.42
  - `home-wifi/kt`: 146.75.51.42
  - `home-wifi/system(2회차)`: 151.101.131.42, 151.101.195.42, 151.101.3.42, 151.101.67.42
  - `tethering/system`: 146.75.51.42
  - `tethering/google`: 151.101.131.42, 151.101.195.42, 151.101.3.42, 151.101.67.42
  - `tethering/quad9`: 151.101.131.42, 151.101.195.42, 151.101.3.42, 151.101.67.42
  - `tethering/kt`: 146.75.51.42
  - `tethering/system(2회차)`: 146.75.51.42

**`www.github.com`** — 서로 다른 주소 집합 2개
  - `home-wifi/system`: 20.200.245.247
  - `home-wifi/google`: 20.200.245.247
  - `home-wifi/quad9`: 20.205.243.166
  - `home-wifi/kt`: 20.200.245.247
  - `home-wifi/system(2회차)`: 20.200.245.247
  - `tethering/system`: 20.200.245.247
  - `tethering/google`: 20.200.245.247
  - `tethering/quad9`: 20.205.243.166
  - `tethering/kt`: 20.200.245.247
  - `tethering/system(2회차)`: 20.200.245.247

**`www.wikipedia.org`** — 서로 다른 주소 집합 1개
  - `home-wifi/system`: 103.102.166.224
  - `home-wifi/google`: 103.102.166.224
  - `home-wifi/quad9`: 103.102.166.224
  - `home-wifi/kt`: 103.102.166.224
  - `home-wifi/system(2회차)`: 103.102.166.224
  - `tethering/system`: 103.102.166.224
  - `tethering/google`: 103.102.166.224
  - `tethering/quad9`: 103.102.166.224
  - `tethering/kt`: 103.102.166.224
  - `tethering/system(2회차)`: 103.102.166.224

**`www.nytimes.com`** — 서로 다른 주소 집합 2개
  - `home-wifi/system`: 151.101.1.164, 151.101.129.164, 151.101.193.164, 151.101.65.164
  - `home-wifi/google`: 151.101.1.164, 151.101.129.164, 151.101.193.164, 151.101.65.164
  - `home-wifi/quad9`: 151.101.1.164, 151.101.129.164, 151.101.193.164, 151.101.65.164
  - `home-wifi/kt`: 146.75.49.164
  - `home-wifi/system(2회차)`: 151.101.1.164, 151.101.129.164, 151.101.193.164, 151.101.65.164
  - `tethering/system`: 146.75.49.164
  - `tethering/google`: 151.101.1.164, 151.101.129.164, 151.101.193.164, 151.101.65.164
  - `tethering/quad9`: 151.101.1.164, 151.101.129.164, 151.101.193.164, 151.101.65.164
  - `tethering/kt`: 146.75.49.164
  - `tethering/system(2회차)`: 146.75.49.164

## 규칙이 틀린 곳

- `www.wikipedia.org` — 순진한 규칙(마지막 두 라벨)은 **제3자**라고 했지만 실제로는 **자체**다. 사슬이 wikimedia.org 안에서 끝남 (자체 CDN)

자세한 해석은 `observation.md`.
