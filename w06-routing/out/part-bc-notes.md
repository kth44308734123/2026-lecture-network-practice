# Part B and C measurement notes (facts only; observation.md is NOT written here)

Environment: Docker Desktop, 3 containers r1 r2 r3, image frrouting/frr:v9.1.0 (local tag of quay.io/frrouting/frr:9.1.0), `docker compose --profile routing`.
Timing tool: /private scratchpad Python poller (not part of repo): 3 threads each polling `vtysh -c "show ip route ospf" -c "show ip ospf neighbor"` continuously (~0.1 s/poll), time.time() stamps, t=0 right before the triggering command. Resolution ~0.1 s. Raw logs in this folder: log-cut.txt, log-restore.txt, log-silent.txt, log-silent-heal.txt, log-cost.txt, log-cost-reset.txt.

## Topology as actually wired (anomaly: eth names do not match the frr.conf descriptions)
Command: `docker compose exec -T rX ip -br addr`
- r1: eth0 172.18.0.3/16, eth1 172.19.0.3/16
- r2: eth0 172.18.0.2/16, eth1 172.20.0.3/16
- r3: eth0 172.19.0.2/16, eth1 172.20.0.2/16
So 172.18/16 = r1-r2, 172.19/16 = r1-r3, 172.20/16 = r2-r3. frr.conf comments say r1 eth0 = "net_a (r1-r3)" and eth1 = "net_b (r1-r2)"; real wiring is the opposite.
Consequence: scenario.sh `cut` (r1 eth1 down) cuts the r1-r3 link, and `cost` (r1 eth0) changes the r1-r2 link. All networks are /16.

## Neighbor states (before)
Command: `show ip ospf neighbor` on each router (saved in route-before.txt). All adjacencies Full:
r1: 2.2.2.2 Full/DR (eth0), 3.3.3.3 Full/DR (eth1). r2: 1.1.1.1 Full/Backup (eth0), 3.3.3.3 Full/DR (eth1). r3: 1.1.1.1 Full/Backup (eth0), 2.2.2.2 Full/Backup (eth1).
(Each /16 is a broadcast network, so DR/Backup/DROther roles appear on it.) First seen Full about 27-32 s after `up`.

## B1 route-before.txt (`show ip route ospf`, noise filtered)
r1: 172.18/16 direct eth0 [110/10]; 172.19/16 direct eth1 [110/10]; 172.20/16 [110/20] ECMP via 172.18.0.2 eth0 and 172.19.0.2 eth1
r2: 172.18/16 direct eth0 [110/10]; 172.20/16 direct eth1 [110/10]; 172.19/16 [110/20] ECMP via 172.18.0.3 eth0 and 172.20.0.2 eth1
r3: 172.19/16 direct eth0 [110/10]; 172.20/16 direct eth1 [110/10]; 172.18/16 [110/20] ECMP via 172.19.0.3 eth0 and 172.20.0.3 eth1

## B2 learned (not directly attached) routes
Command: `show ip route ospf`; LSDB checked with `show ip ospf database` (all three routers hold identical 3 Router LSAs 1.1.1.1/2.2.2.2/3.3.3.3, seq 0x80000006, plus 3 Network LSAs 172.18.0.2 (adv 2.2.2.2), 172.19.0.2 (adv 3.3.3.3), 172.20.0.2 (adv 3.3.3.3)).
- r1 learned 172.20.0.0/16 (cost 20, two equal paths)
- r2 learned 172.19.0.0/16 (cost 20, two equal paths)
- r3 learned 172.18.0.0/16 (cost 20, two equal paths)
Each router learned exactly the one subnet it has no interface on. (Directly attached subnets also show as "O ... is directly connected" with cost 10.)

## Hello/dead intervals
`grep -n "hello\|dead" topology/*/frr.conf` -> no match; the frr.conf files only set `ip ospf cost 10` and `network 0.0.0.0/0 area 0`.
`show ip ospf interface` (every interface on every router): "Timer intervals configured, Hello 10s, Dead 40s, Wait 40s, Retransmit 5". These are FRR defaults.

## B3/B4 cut: r1 `ip link set eth1 down` (r1-r3 link, 172.19/16)
route-after.txt = tables ~45 s after the cut:
r1: 172.18/16 direct [110/10]; 172.19/16 [110/30] via 172.18.0.2 eth0; 172.20/16 [110/20] via 172.18.0.2 eth0
r2: 172.18/16 direct; 172.19/16 [110/20] via 172.20.0.2 eth1 (r3 only); 172.20/16 direct
r3: 172.18/16 [110/20] via 172.20.0.3 eth1 (r2 only); 172.19/16 direct; 172.20/16 direct
Timing: all three tables correct at the first poll after the cut, t <= +0.13 s. r1 noticed by kernel link-down (immediate); r2 and r3 by LSA from r1. r3 removed neighbor r1 from its neighbor list only at +31.14 s (dead timer), but its routing was already correct. Details in reconverge.txt.
Note: because of link-down detection, this measurement does NOT exercise the 40 s dead interval. scenario.sh's own 1 s polling would report "1 sec" (it has 1 s granularity and starts polling after sleep 1).

## Silent failure variant (worked, no repo files touched)
Command: `docker compose exec -T r3 iptables -A INPUT -i eth0 -j DROP` and same with `-A OUTPUT -o eth0` (r3 eth0 = r3-r1 link). Carrier stays up.
r3 declared r1 dead at +33.08 s; r1 and r2 tables changed at +33.09 s via LSA flood; r1 declared r3 dead at +38.87 s. Consistent with Dead 40 s (40 s minus 0-10 s since last hello).
Healed with `iptables -D` (both rules; `iptables -S` on r3 shows policies ACCEPT, no rules): Full at +5.33 s, tables equal before-state at +11.13 s.
Anomaly/observation: during the silent failure, after r1's dead timer fired (+38.87 s) r2 again lists ECMP to 172.19/16 via r1, since r1 still has an (unreachable-to-r3) interface in 172.19/16; the final stable table of this state is not the same as the post-cut table above.

## B5 restore: r1 `ip link set eth1 up`
Tables all equal to before-state after 10.90 s (r1 5.92 s, r3 10.90 s; r2 already at +0.17 s). Adjacency r1-r3 Full at +5.84 s. Details in reconverge.txt.
Quirks seen: r2 added the ECMP route via r1 at +0.17 s, before the r1-r3 adjacency was Full; r1 briefly (+5.84 to +5.92 s) showed 172.19/16 as cost 30 via r2 instead of direct.

## Part C cost change (no link down)
cost-before.txt / cost-after.txt. Command: `vtysh -c "configure terminal" -c "interface eth0" -c "ip ospf cost 100"` on r1 (eth0 = r1-r2 link, 172.18/16), by hand (scenario.sh's trailing `sleep 15` skipped).
After (cost-after.txt): r1: 172.18/16 [110/30] via 172.19.0.2 eth1 (reaches its own subnet through r3!); 172.19/16 direct; 172.20/16 [110/20] via 172.19.0.2 eth1 only (ECMP gone). r2 and r3 tables unchanged except r3 172.18/16 loses ECMP via r1: r3 shows [110/20] via 172.20.0.3 eth1 only. r2 172.19/16 stays ECMP via r1 and r3.
Timing: r1 and r3 tables changed at t <= +0.15 s (first poll after); r2's table did not change. Both link interfaces stayed up, neighbors remained Full throughout.
Reset: `ip ospf cost 10` on eth0; r1 and r3 back to before-state at <= +0.13 s. Final state of all 3 routers verified identical to route-before.txt (uptimes stripped). `show ip ospf interface` r1: eth0 cost 10, eth1 cost 10.

## State left behind
r1 r2 r3 containers running, r1 eth1 up, r3 iptables clean, cost 10 everywhere, neighbors Full, tables equal to before-state.
Files in this folder besides required ones: log-*.txt raw event logs. observation.md not touched.
Failed attempts: none, except my first shell loop failed due to zsh `==` quirk (no effect on the network).
