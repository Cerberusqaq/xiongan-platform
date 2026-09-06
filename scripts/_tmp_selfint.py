import math
import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')

def seg_inter(a1, a2, b1, b2):
    """两线段是否真交叉（含端点邻近 → True 表示自交候选）。"""
    def ccw(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
    d1 = ccw(b1, b2, a1); d2 = ccw(b1, b2, a2)
    d3 = ccw(a1, a2, b1); d4 = ccw(a1, a2, b2)
    return d1*d2 < 0 and d3*d4 < 0

def self_intersections(pts):
    n = len(pts)
    hits = []
    for i in range(n - 1):
        for j in range(i + 2, n - 1):
            if j == i + 1:
                continue
            if seg_inter(pts[i], pts[i+1], pts[j], pts[j+1]):
                hits.append((i, j))
    return hits

targets = ['E7_14', 'E14_7', 'E7_3', 'E3_7', 'E7_5', 'E5_7', 'E10_19', 'E19_10',
           'E2_19', 'E19_2', 'E8_18', 'E18_8', 'E12_18', 'E18_12', 'E17_18', 'E18_17',
           'E20_18', 'E18_20']
for eid in targets:
    e = net.getEdge(eid)
    if e is None:
        continue
    for li, lane in enumerate(e.getLanes()):
        s = lane.getShape()
        hits = self_intersections(s)
        if hits:
            print(f'{eid}_lane{li}: 自交 {len(hits)} 处，首例 idx {hits[:3]}')
