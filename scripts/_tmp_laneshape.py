import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')
bad = 0
for e in net.getEdges():
    ls = [len(l.getShape()) for l in e.getLanes()]
    if len(set(ls)) > 1:
        bad += 1
        if bad <= 12:
            print(f'{e.getID()}: lane点数列={ls}')
print('点数不一致的边数:', bad, '/', len(net.getEdges()))
# 抽查一段弯道：lane0 vs lane1 相邻采样间距是否均匀
for eid in ['E14_7', 'E12_18', 'E10_19']:
    e = net.getEdge(eid)
    if e is None:
        continue
    for li, l in enumerate(e.getLanes()):
        s = l.getShape()
        segs = [round(__import__('math').hypot(s[i][0]-s[i-1][0], s[i][1]-s[i-1][1]), 2) for i in range(1, len(s))]
        print(eid, f'lane{li}', '点', len(s), '段距 min/max', min(segs) if segs else None, max(segs) if segs else None)
