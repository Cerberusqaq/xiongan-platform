import math
import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')

def nearest_dual_gap(a_lanes, b_lanes):
    """两方向全部车道点集的最近距离（近似检查双向是否重叠/已分开）。"""
    pa = [p for l in a_lanes for p in l.getShape()]
    pb = [p for l in b_lanes for p in l.getShape()]
    # 抽样加速
    best = 1e9
    for i in range(0, len(pa), 3):
        for j in range(0, len(pb), 3):
            d = math.hypot(pa[i][0]-pb[j][0], pa[i][1]-pb[j][1])
            if d < best:
                best = d
    return best

pairs = set()
for e in net.getEdges():
    f, t = e.getFromNode().getID(), e.getToNode().getID()
    other = net.getEdge(f'{t}_{f}') if net.hasEdge(f'{t}_{f}') else None
    if other is not None:
        pairs.add(tuple(sorted([e.getID(), other.getID()])))

print('双向对最小间隙（>0 即 laneShapes 已分开，无需再平移）:')
for a, b in sorted(pairs):
    ea, eb = net.getEdge(a), net.getEdge(b)
    g = nearest_dual_gap(ea.getLanes(), eb.getLanes())
    print(f'  {a} / {b}: {g:.2f} m')
