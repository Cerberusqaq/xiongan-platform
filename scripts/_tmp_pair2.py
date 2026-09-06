import sumolib

net = sumolib.net.readNet(r'C:\Users\27773\Desktop\xiongan_v5.1\networks\network\base_network.net.xml')
pairs = [('E14_7', 'E7_14'), ('E12_18', 'E18_12'), ('E2_19', 'E19_2'), ('E20_18', 'E18_20')]
for a, b in pairs:
    ea, eb = net.getEdge(a), net.getEdge(b)
    if ea is None or eb is None:
        continue
    print(f'--- {a} vs {b} ---')
    for name, e in ((a, ea), (b, eb)):
        for li, l in enumerate(e.getLanes()):
            s = l.getShape()
            print(f'  {name}_lane{li}: 首{s[0]} 尾{s[-1]}')
