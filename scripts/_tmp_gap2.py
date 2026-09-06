import math
import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')
by_pair = {}
for e in net.getEdges():
    by_pair.setdefault((e.getFromNode().getID(), e.getToNode().getID()), []).append(e)

def min_gap(a, b):
    pa = [p for l in a for p in l.getShape()]
    pb = [p for l in b for p in l.getShape()]
    best = 1e9
    for i in range(0, len(pa), 4):
        for j in range(0, len(pb), 4):
            d = math.hypot(pa[i][0]-pb[j][0], pa[i][1]-pb[j][1])
            if d < best:
                best = d
    return best

seen = set()
rows = []
for (f, t), es in by_pair.items():
    rev = by_pair.get((t, f), [])
    if not rev:
        continue
    for a in es:
        for b in rev:
            key = tuple(sorted([a.getID(), b.getID()]))
            if key in seen:
                continue
            seen.add(key)
            g = min_gap(a.getLanes(), b.getLanes())
            rows.append((g, a.getID(), b.getID()))
rows.sort()
print('双向 laneShapes 最近间距（m）—— 最小 10 对 & 最大 10 对:')
for g, a, b in rows[:10] + rows[-5:]:
    print(f'  {g:6.2f}  {a} / {b}')
print('全部 > 3m 的对数:', sum(1 for g, *_ in rows if g > 3), '/', len(rows))
