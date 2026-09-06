import math
import json
import urllib.request

# 读取后端 preview-data（与画布同源 lane_shapes）
u = ('http://127.0.0.1:8020/api/v1/networks/preview-data?net_path='
     + urllib.request.quote(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml'))
gj = json.loads(urllib.request.urlopen(u, timeout=30).read())['data']
lane_shapes = {}
for f in gj['features']:
    if f['geometry']['type'] == 'LineString':
        lane_shapes[f['properties']['edge_id']] = f['properties'].get('lane_shapes') or []

def screen_pts(pts, off_px):
    """复现前端 screenShape：y 翻转 + 逐点法线平移 off_px。"""
    S = 1.0  # 平移量用像素等价；法线方向与 S 无关
    P = [[x * S, -y * S] for x, y in pts]
    for i in range(len(P)):
        a = P[max(0, i - 1)]; b = P[min(len(P) - 1, i + 1)]
        dx = b[0] - a[0]; dy = b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        P[i] = [P[i][0] + (-dy / L) * off_px, P[i][1] + (dx / L) * off_px]
    return P

def seg_inter(a1, a2, b1, b2):
    def ccw(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
    return ccw(a1,a2,b1)*ccw(a1,a2,b2) < 0 and ccw(b1,b2,a1)*ccw(b1,b2,a2) < 0

def selfint(pts):
    n = len(pts); h = 0
    for i in range(n - 1):
        for j in range(i + 2, n - 1):
            if seg_inter(pts[i], pts[i+1], pts[j], pts[j+1]):
                h += 1
    return h

targets = ['E7_14', 'E14_7', 'E7_3', 'E3_7', 'E7_5', 'E5_7', 'E10_19', 'E19_10',
           'E2_19', 'E19_2', 'E8_18', 'E18_8', 'E12_18', 'E18_12', 'E17_18', 'E18_17',
           'E20_18', 'E18_20']
print('边 | lane | off=0 自交 | off=5m 自交')
for eid in targets:
    for li, sh in enumerate(lane_shapes.get(eid, [])):
        s0 = selfint(screen_pts(sh, 0))
        s5 = selfint(screen_pts(sh, 5.0))
        if s5:
            print(f'{eid} lane{li}: off0={s0}  off5={s5}')
