import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')
# 弯道对：两个方向的 edge，各车道首尾 + 彼此间距
pairs = [('E14_7', 'E7_14'), ('E12_18', 'E18_12'), ('E8_18', 'E18_8'),
         ('E2_19', 'E19_2'), ('E20_18', 'E18_20'), ('E7_5', 'E5_7')]
for a, b in pairs:
    ea, eb = net.getEdge(a), net.getEdge(b)
    if ea is None or eb is None:
        continue
    for name, e in ((a, ea), (b, eb)):
        pts = e.getLanes()[0].getShape()
        print(f'{name} lane0 首 {pts[0]} 尾 {pts[-1]}')
    # 两个方向最近车道的最小间隙（采样近似）
    la = [p for l in ea.getLanes() for p in l.getShape()]
    lb = [p for l in eb.getLanes() for p in l.getShape()]
    print()
