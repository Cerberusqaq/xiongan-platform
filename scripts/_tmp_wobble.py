import math
import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')

def wobble(pts):
    """绝对方向角序列 → 相邻段转角增量(deg) 分布 + 符号交替率。"""
    if len(pts) < 3:
        return 0, 0.0, 0.0
    dts = []
    for i in range(1, len(pts)):
        a = math.degrees(math.atan2(pts[i][1]-pts[i-1][1], pts[i][0]-pts[i-1][0]))
        if i > 1:
            d = (a - dts[-1][1] + 180) % 360 - 180   # [-180,180]
            dts.append((d, a))
        else:
            dts.append((0.0, a))
    turns = [d for d, _ in dts[1:]]
    avg_turn = sum(abs(d) for d in turns) / max(1, len(turns))
    flips = sum(1 for i in range(1, len(turns)) if turns[i] * turns[i-1] < 0)
    rate = flips / max(1, len(turns))
    return avg_turn, rate, max(abs(d) for d in turns) if turns else 0.0

rows = []
for e in net.getEdges():
    for li, lane in enumerate(e.getLanes()):
        s = lane.getShape()
        avg, rate, mx = wobble(s)
        rows.append((avg, rate, mx, e.getID(), li, len(s)))
rows.sort(reverse=True)
print('lane 平均单段转角(°) top20（大=麻花）:')
for avg, rate, mx, eid, li, n in rows[:20]:
    print(f'  平均转角{avg:6.1f}° 交替率{rate:.2f} 最大{int(mx)}°  {eid}_lane{li} 点{n}')
