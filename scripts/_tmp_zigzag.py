import math
import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')
print('edges:', len(net.getEdges()), 'total lanes:', sum(len(e.getLanes()) for e in net.getEdges()))

def zigzag_score(pts):
    """返回 (折返点占比, 最大折返幅度)。折返=在沿总方向的投影上倒退超过 0.5m。"""
    if len(pts) < 3:
        return 0.0, 0.0
    # 总体方向单位向量（首→尾）
    dx = pts[-1][0] - pts[0][0]; dy = pts[-1][1] - pts[0][1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return 0.0, 0.0
    ux, uy = dx / L, dy / L
    # 沿总方向的累积投影（单调增才正常）
    proj = [0.0]
    for i in range(1, len(pts)):
        proj.append(proj[-1] + (pts[i][0]-pts[i-1][0])*ux + (pts[i][1]-pts[i-1][1])*uy)
    # 折返幅度：某点投影相比局部单调前进的期望后退量
    back = 0.0; nback = 0
    for i in range(1, len(pts)):
        # 与前一折点的最大后退
        expected = proj[i-1] + 0.0
        retreat = expected - proj[i]
        if retreat > 0.5:
            nback += 1
            back = max(back, retreat)
    return nback / max(1, len(pts)-1), back

worst = []
for e in net.getEdges():
    for li, lane in enumerate(e.getLanes()):
        s = lane.getShape()
        r, b = zigzag_score(s)
        if b > 0.3:
            worst.append((b, r, e.getID(), li, len(s)))

worst.sort(reverse=True)
print('存在折返(>0.3m)的 lane 数:', len(worst), '/', sum(len(e.getLanes()) for e in net.getEdges()))
for b, r, eid, li, np_ in worst[:20]:
    print(f'  折返幅 {b:.2f}m 占比 {r:.2f}  {eid}_lane{li} 点数{np_}')
