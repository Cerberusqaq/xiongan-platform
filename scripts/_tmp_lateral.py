import math
import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')

def dist_to_seg(px, py, a, b):
    vx, vy = b[0]-a[0], b[1]-a[1]
    L2 = vx*vx+vy*vy
    if L2 < 1e-9:
        return math.hypot(px-a[0], py-a[1]), 0.0
    t = max(0.0, min(1.0, ((px-a[0])*vx+(py-a[1])*vy)/L2))
    cx, cy = a[0]+t*vx, a[1]+t*vy
    return math.hypot(px-cx, py-cy), 0.0

rows = []
for e in net.getEdges():
    c = e.getShape()
    for li, lane in enumerate(e.getLanes()):
        s = lane.getShape()
        # 期望横向位：lane 数与方向；这里只统计偏差波动（相对首点沿法线的符号）
        # 简单量化：采样点到 edge 中线的垂距沿程是否大幅振荡
        ds = []
        for p in s:
            d, _ = min((dist_to_seg(p[0], p[1], c[i], c[i+1]) for i in range(len(c)-1)))
            ds.append(d)
        spread = max(ds) - min(ds)
        if len(s) >= 4:
            mid_std = 0.0
            rows.append((spread, e.getID(), li, len(s), round(max(ds),1), round(min(ds),1)))
rows.sort(reverse=True)
print('lane 到中线距离波动 top20 (spread=max-min):')
for sp, eid, li, n, mx, mn in rows[:20]:
    print(f'  spread {sp:6.1f}m  {eid}_lane{li} 点{n} 距中线 max{mx} min{mn}')
