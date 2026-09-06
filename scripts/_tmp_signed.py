import math
import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')

def signed_lateral(edge_pts, lane_pts):
    """每个 lane 点相对 edge 中线的有符号横向距离（沿中线前进方向的左为正）。"""
    out = []
    # 预先算每段法线
    segs = []
    for i in range(len(edge_pts) - 1):
        ax, ay = edge_pts[i]; bx, by = edge_pts[i + 1]
        vx, vy = bx - ax, by - ay
        L = math.hypot(vx, vy)
        if L < 1e-9:
            segs.append(None); continue
        segs.append(((ax, ay), (vx / L, vy / L), L))
    for p in lane_pts:
        best = None
        for s in segs:
            if s is None:
                continue
            (ax, ay), (ux, uy), L = s
            t = max(0.0, min(L, (p[0]-ax)*ux + (p[1]-ay)*uy))
            cx, cy = ax + ux * t, ay + uy * t
            d = math.hypot(p[0]-cx, p[1]-cy)
            # 左法线 (-uy, ux)，signed
            sgn = (p[0]-cx)*(-uy) + (p[1]-cy)*ux
            if best is None or d < best[0]:
                best = (d, sgn)
        out.append(best[1] if best else 0.0)
    return out

def flips(sig):
    """signed 序列符号翻转次数（跳过近 0）。"""
    n = 0
    prev = None
    for v in sig:
        s = 1 if v > 0.05 else (-1 if v < -0.05 else None)
        if s is None:
            continue
        if prev is not None and s != prev:
            n += 1
        prev = s
    return n

targets = ['E7_14', 'E14_7', 'E7_3', 'E3_7', 'E7_5', 'E5_7', 'E10_19', 'E19_10',
           'E2_19', 'E19_2', 'E8_18', 'E18_8', 'E12_18', 'E18_12', 'E17_18', 'E18_17',
           'E20_18', 'E18_20']
for eid in targets:
    e = net.getEdge(eid)
    if e is None:
        continue
    c = e.getShape()
    for li, lane in enumerate(e.getLanes()):
        s = signed_lateral(c, lane.getShape())
        print(f'{eid}_lane{li}: 翻转{flips(s)}  min={min(s):.2f} max={max(s):.2f} 点数{len(s)}')
