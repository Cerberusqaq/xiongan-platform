<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { apiGet, apiPost } from '../api/http'
import { subscribe } from '../realtime'
import { useUiStore } from '../stores/ui'
import { useSimStore } from '../stores/sim'
import { useEventStore } from '../stores/events'
import { useMetricsStore } from '../stores/metrics'

const ui = useUiStore()
const sim = useSimStore()
const events = useEventStore()
const metrics = useMetricsStore()

// 扰动事件 → 受影响边高亮（road 变色 + 中点脉冲标记）
// 注意：三种事件色均避开琥珀色系（琥珀用于"选中道路"标记，避免混淆）
const EVENT_COLORS = { accident: '#ff6b6b', construction: '#b197fc', large_event: '#4ecdc4' }
const eventEdges = new Map() // edgeId -> {color, type}
watch(() => events.list, (list) => {
  eventEdges.clear()
  for (const ev of list || []) {
    const col = EVENT_COLORS[ev.event_type] || '#ffa94d'
    for (const id of ev.params?.edge_ids || []) {
      if (!eventEdges.has(id)) eventEdges.set(id, { color: col, type: ev.event_type })
    }
  }
}, { deep: true, immediate: true })

const canvas = ref(null)
const hint = ref('请先启动仿真以加载路网')
const netName = ref('')   // 路网中文名（主标题）
const netFile = ref('')   // 路网文件名（副标题）

// ── 数据状态 ──────────────────────────────────────────────
const edges = ref([])          // {pts, lanes, speed, id, from, to, off(世界偏移), partnerId, contTo, contFrom}
const edgeMap = new Map()
const contMap = new Map()      // (备用) 边 id -> 延续边
const nodes = ref([])
const tlsById = new Map()
const vehicles = new Map()     // id -> {x,y,angle,px,py,t0,type,speed}
const tlsData = new Map()      // tls_id -> {state_str, links}
const colors = ref({})

const view = { scale: 1, tx: 0, ty: 0 }
// 世界→屏幕（模块级，供命中检测等 draw() 之外使用）
const X = (x) => x * view.scale + view.tx
const Y = (y) => -y * view.scale + view.ty
let bounds = null
let raf = 0
let lastBatchAt = 0
let stepMs = 1000
let unsubs = []

// 类型颜色（仅非默认类型生效，如 bus/fleet/truck/bicycle）
const TYPE_COLORS = { bus: '#ff6b6b', fleet: '#ffa94d', truck: '#b197fc', bicycle: '#63e6be' }
// SUMO 类型 id → 中文名（DEFAULT_VEHTYPE 是 SUMO 默认小汽车）
const VEH_TYPE_LABELS = {
  DEFAULT_VEHTYPE: '小汽车',
  passenger: '小汽车',
  car: '小汽车',
  bus: '公交车',
  truck: '货车',
  bicycle: '自行车',
  fleet: '车队车辆',
}
const MAX_SPEED = 13.89 // base_network 主干道限速，用于速度归一化

function refreshColors() {
  const cs = getComputedStyle(document.documentElement)
  const v = (n) => cs.getPropertyValue(n).trim()
  colors.value = {
    bg: v('--canvas-bg'), edge: v('--net-edge'), edgeHi: v('--net-edge-highlight'),
    node: v('--net-node'), text3: v('--text-3'), border: v('--border'),
    borderStrong: v('--border-strong'), green: v('--signal-green'), red: v('--signal-red'),
    accent: v('--accent'), greenSoft: v('--signal-green-soft'), redSoft: v('--signal-red-soft'),
  }
}
watch(() => ui.theme, refreshColors)

// ── 路网加载 ──────────────────────────────────────────────
/** 清空画布全部状态（停止/无路网时调用，避免残留旧路网图形） */
function clearNet() {
  edges.value = []
  nodes.value = []
  edgeMap.clear()
  tlsById.clear()
  vehicles.clear()
  tlsData.clear()
  sim.currentEdges = []
  bounds = null
}

async function loadNetwork() {
  try {
    const gj = await apiGet('/network')
    const feats = gj.features || []
    if (!feats.length) { clearNet(); hint.value = '请先启动仿真以加载路网'; return }
    parseGeo(feats)
    const running = sim.nets.find((n) => n.net_path === sim.lastNetPath)
    if (running) {
      netName.value = running.label || running.name
      netFile.value = running.name
    } else {
      netName.value = '当前路网'
      netFile.value = ''
    }
    hint.value = ''
    fitView()
  } catch {
    hint.value = '后端未连接'
  }
}

function parseGeo(feats) {
  edges.value = []
  nodes.value = []
  edgeMap.clear()
  tlsById.clear()
  const byPair = new Map()
  for (const f of feats) {
    if (f.geometry.type === 'LineString') {
      const e = {
        id: f.properties.edge_id,
        from: f.properties.from_node,
        to: f.properties.to_node,
        pts: f.geometry.coordinates,
        lanes: f.properties.lanes || 1,
        speed: f.properties.speed_limit || 0,
        laneShapes: f.properties.lane_shapes || null,
        off: 0,
        partnerId: null,
        contTo: null,
        contFrom: null,
      }
      edges.value.push(e)
      edgeMap.set(e.id, e)
      byPair.set(`${e.from}|${e.to}`, e)
    } else if (f.geometry.type === 'Point') {
      const [x, y] = f.geometry.coordinates
      const idx = nodes.value.length
      nodes.value.push({ x, y, tls: !!f.properties.tls_id, id: f.properties.node_id })
      if (f.properties.tls_id) tlsById.set(f.properties.tls_id, idx)
    }
  }
  // 双向配对：同一条路的两个方向各自偏移（半宽 + 中缝），中间留出分隔线
  for (const e of edges.value) {
    if (e.off !== 0 || e.partnerId) continue
    const p = byPair.get(`${e.to}|${e.from}`)
    if (p && p !== e) {
      const off = (e.lanes * 3.2) / 2 + 1.8
      e.off = off
      p.off = off
      e.partnerId = p.id
      p.partnerId = e.id
    }
  }
  // 同向延续边（路口对侧同一条路的同向段）：车道线穿过路口时相接
  contMap.clear()
  const fromMap = new Map()
  const toMap = new Map()
  for (const e of edges.value) {
    if (!fromMap.has(e.from)) fromMap.set(e.from, [])
    if (!toMap.has(e.to)) toMap.set(e.to, [])
    fromMap.get(e.from).push(e)
    toMap.get(e.to).push(e)
  }
  for (const e of edges.value) {
    if (!e.off) continue
    const n = e.pts.length
    // e.to 侧的延续（方向一致）
    const ax = e.pts[n - 1][0] - e.pts[n - 2][0]
    const ay = e.pts[n - 1][1] - e.pts[n - 2][1]
    const al = Math.hypot(ax, ay) || 1
    for (const c of fromMap.get(e.to) || []) {
      if (c.id === e.id || c.id === e.partnerId || !c.off) continue
      const bx = c.pts[1][0] - c.pts[0][0], by = c.pts[1][1] - c.pts[0][1]
      if ((ax * bx + ay * by) / (al * (Math.hypot(bx, by) || 1)) > 0.85) { e.contTo = c; break }
    }
    // e.from 侧的延续
    const a0x = e.pts[1][0] - e.pts[0][0], a0y = e.pts[1][1] - e.pts[0][1]
    const a0l = Math.hypot(a0x, a0y) || 1
    for (const d of toMap.get(e.from) || []) {
      if (d.id === e.id || d.id === e.partnerId || !d.off) continue
      const m = d.pts.length
      const bx = d.pts[m - 1][0] - d.pts[m - 2][0], by = d.pts[m - 1][1] - d.pts[m - 2][1]
      if ((a0x * bx + a0y * by) / (a0l * (Math.hypot(bx, by) || 1)) > 0.85) { e.contFrom = d; break }
    }
  }
  sim.currentEdges = edges.value.map((e) => e.id)
  computeBounds()
}

function computeBounds() {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const e of edges.value) for (const [x, y] of e.pts) {
    if (x < minX) minX = x; if (x > maxX) maxX = x
    if (y < minY) minY = y; if (y > maxY) maxY = y
  }
  for (const n of nodes.value) {
    if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x
    if (n.y < minY) minY = n.y; if (n.y > maxY) maxY = n.y
  }
  bounds = { minX, minY, maxX, maxY, w: maxX - minX || 1, h: maxY - minY || 1 }
}

function fitView() {
  const el = canvas.value
  if (!el || !bounds) return
  const W = el.clientWidth, H = el.clientHeight
  const pad = 60
  view.scale = Math.min((W - pad * 2) / bounds.w, (H - pad * 2) / bounds.h)
  view.scale = Math.max(view.scale, 0.01)
  // Y 翻转：SUMO y 朝北，屏幕 y 朝下 → 北在上、右行
  view.tx = (W - bounds.w * view.scale) / 2 - bounds.minX * view.scale
  view.ty = (H - bounds.h * view.scale) / 2 + bounds.maxY * view.scale
}

// ── WS 实时数据 ───────────────────────────────────────────
/** 边 pts 上离 (wx,wy) 最近线段的屏幕方向角（弧度，atan2 约定，Y 翻转取负） */
function edgeHeadingAt(e, wx, wy) {
  let best = Infinity, ang = 0
  const P = e.pts
  for (let i = 0; i < P.length - 1; i++) {
    const ax = P[i][0], ay = P[i][1], bx = P[i + 1][0], by = P[i + 1][1]
    const dx = bx - ax, dy = by - ay
    const len2 = dx * dx + dy * dy || 1
    let t = ((wx - ax) * dx + (wy - ay) * dy) / len2
    t = Math.max(0, Math.min(1, t))
    const cx = ax + dx * t, cy = ay + dy * t
    const d2 = (wx - cx) * (wx - cx) + (wy - cy) * (wy - cy)
    if (d2 < best) { best = d2; ang = Math.atan2(-dy, dx) }
  }
  return ang
}

/** 车辆初始朝向：优先按所在车道边的切线方向——SUMO 对刚生成（depart 瞬间）
    车辆的角度不可靠（常为默认 0），第一帧位移为零也无法用移动方向推导；
    找不到边（连接器上）时回退 SUMO angle（Y 翻转取负） */
function initHeading(v) {
  if (v.lane) {
    const lp = v.lane.split('_')
    lp.pop()
    const e = edgeMap.get(lp.join('_'))
    if (e && e.pts && e.pts.length >= 2) return edgeHeadingAt(e, v.x, v.y)
  }
  return -((v.angle || 0) * Math.PI) / 180
}

function handleVehicles(d) {
  if (!d) return
  const now = performance.now()
  if (lastBatchAt) {
    const delta = now - lastBatchAt
    stepMs = stepMs * 0.7 + Math.min(3000, Math.max(50, delta)) * 0.3
  }
  lastBatchAt = now
  for (const v of d.added || []) {
    vehicles.set(v.id, {
      ...v, px: v.x, py: v.y, t0: now,
      heading: initHeading(v),
    })
  }
  for (const v of d.updated || []) {
    const cur = vehicles.get(v.id)
    if (cur) {
      cur.px = cur.x; cur.py = cur.y
      Object.assign(cur, v)
      cur.t0 = now
    } else {
      vehicles.set(v.id, {
        ...v, px: v.x, py: v.y, t0: now,
        heading: initHeading(v),
      })
    }
  }
  for (const id of d.removed || []) vehicles.delete(id)
}

function handleTls(d) {
  if (!d) return
  for (const [tid, st] of Object.entries(d)) {
    tlsData.set(tid, { state_str: st.state_str || '', links: st.links || [] })
  }
}

// ── 渲染工具 ──────────────────────────────────────────────
function stateColor(ch, col) {
  if (/[Gg]/.test(ch)) return col.green
  if (/y/.test(ch)) return col.accent
  if (/[Rr]/.test(ch)) return col.red
  return col.text3
}

/** 世界点列 → 屏幕（可选横向偏移 offPx + 附加 extra，沿屏幕垂直方向） */
function screenShape(pts, offPx, extra = 0) {
  const S = view.scale
  const P = pts.map(([x, y]) => [x * S + view.tx, -y * S + view.ty])
  const total = offPx + extra
  if (total) {
    for (let i = 0; i < P.length; i++) {
      const a = P[Math.max(0, i - 1)], b = P[Math.min(P.length - 1, i + 1)]
      const dx = b[0] - a[0], dy = b[1] - a[1]
      const len = Math.hypot(dx, dy) || 1
      P[i] = [P[i][0] + (-dy / len) * total, P[i][1] + (dx / len) * total]
    }
  }
  return P
}

/** 截断世界点列两端各 cut 米（路口处车道线/虚线停车，保留中段） */
function trimPolyline(pts, cut) {
  const n = pts.length
  if (n < 2 || cut <= 0) return pts.slice()
  const cum = [0]
  for (let i = 1; i < n; i++) {
    cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
  }
  const total = cum[n - 1]
  if (total <= cut * 2 + 0.1) return [pts[0], pts[n - 1]]
  const interp = (i, d) => {
    const f = (d - cum[i]) / (cum[i + 1] - cum[i])
    return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f,
            pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f]
  }
  let i0 = 0
  while (i0 < n - 2 && cum[i0 + 1] < cut) i0++
  const out = [interp(i0, cut)]
  for (let i = i0 + 1; i < n - 1; i++) out.push(pts[i])
  let i1 = n - 1
  while (i1 > 1 && cum[i1 - 1] > total - cut) i1--
  out.push(interp(i1 - 1, total - cut))
  return out
}

/** 屏幕空间的多段线（整体横向偏移 offPx + 附加不渐隐偏移 extra，均沿屏幕垂直方向） */
function polyScreen(e, offPx, extra = 0) {
  return screenShape(e.pts, offPx, extra)
}

/** 画一条连接线（路口处同向延续边之间的缺口） */
function traceConn(ctx, a, b) {
  ctx.beginPath()
  ctx.moveTo(a[0], a[1])
  ctx.lineTo(b[0], b[1])
  ctx.stroke()
}

function tracePoly(ctx, P) {
  ctx.beginPath()
  ctx.moveTo(P[0][0], P[0][1])
  for (let i = 1; i < P.length; i++) ctx.lineTo(P[i][0], P[i][1])
  ctx.stroke()
}

// ── 渲染主循环 ────────────────────────────────────────────
function draw(t) {
  const el = canvas.value
  if (!el) return
  const ctx = el.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const W = el.clientWidth, H = el.clientHeight
  if (el.width !== W * dpr || el.height !== H * dpr) { el.width = W * dpr; el.height = H * dpr }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, W, H)

  const c = colors.value
  const S = view.scale
  const X = (x) => x * S + view.tx
  const Y = (y) => -y * S + view.ty
  const laneSep = Math.max(2.6, 3.2 * S)

  // 1) 道路：真实车道几何（SUMO lane shape）或公式回退；同向延续边在路口相接
  ctx.lineCap = 'round'
  const medians = new Set()
  const contOff = (x) => (x && x.off ? Math.max(3.5, x.off * S) : 0)
  const bedW = Math.max(3.5, 3.2 * S)
  for (const e of edges.value) {
    const offPx = e.off ? Math.max(3.5, e.off * S) : 0
    const n = e.lanes
    const hasReal = e.laneShapes && e.laneShapes.length === n
    const shapes = (off) => e.laneShapes.map((sh) => screenShape(sh, off))
    // 路面（车道级真实几何铺满，含渐变/弯曲）
    ctx.strokeStyle = c.edge
    ctx.lineWidth = hasReal ? bedW : Math.max(3.5, (n * 3.2 + 1.4) * S)
    if (hasReal) {
      for (const P of shapes(offPx)) tracePoly(ctx, P)
    } else {
      tracePoly(ctx, polyScreen(e, offPx, 0))
    }
    // 车道分界线（两端 8m 停车，路口区不画线）
    ctx.lineWidth = Math.max(1, S * 0.8)
    if (hasReal) {
      // 真实车道 shape 先截断两端，再取相邻中线
      const T = e.laneShapes.map((sh) => trimPolyline(sh, 8))
      for (let i = 1; i < n; i++) {
        const A = screenShape(T[i - 1], offPx)
        const B = screenShape(T[i], offPx)
        const mid = A.map((p, k) => [(p[0] + (B[k]?.[0] ?? p[0])) / 2, (p[1] + (B[k]?.[1] ?? p[1])) / 2])
        ctx.strokeStyle = c.edgeHi
        tracePoly(ctx, mid)
      }
    } else {
      for (let i = 0; i < n; i++) {
        const laneOff = (i - (n - 1) / 2) * laneSep
        ctx.strokeStyle = i === 0 ? c.edgeHi : c.edge
        tracePoly(ctx, polyScreen(e, offPx, laneOff))
      }
    }
    // 路口连接（同向延续边：仅路面粗线补缺口，路口内不画分界线）
    const laneEnd = (E, i, off) => {
      const P = E.laneShapes ? screenShape(E.laneShapes[i], off) : polyScreen(E, off, (i - (E.lanes - 1) / 2) * laneSep)
      return P
    }
    const bridge = (C, fromSide) => {
      const cOff = contOff(C)
      for (let i = 0; i < n && i < C.lanes; i++) {
        const A = laneEnd(e, i, offPx)
        const B = laneEnd(C, i, cOff)
        const p1 = fromSide ? A[0] : A[A.length - 1]
        const p2 = fromSide ? B[B.length - 1] : B[0]
        ctx.strokeStyle = c.edge
        ctx.lineWidth = bedW
        traceConn(ctx, p1, p2)
      }
    }
    if (e.contTo) bridge(e.contTo, false)
    if (e.contFrom) bridge(e.contFrom, true)
    // 中央分隔线（双向道路，每对只画一次；两端停车，路口区不画）
    if (ui.settings.showMedian && e.off && e.partnerId && !medians.has(e.id) && !medians.has(e.partnerId)) {
      medians.add(e.id)
      medians.add(e.partnerId)
      ctx.strokeStyle = c.borderStrong
      ctx.lineWidth = Math.max(1, S * 0.9)
      ctx.setLineDash([5, 4])
      const M = screenShape(trimPolyline(e.pts, 8), 0, 0)
      tracePoly(ctx, M)
      ctx.setLineDash([])
    }
  }

  // 1.5) 扰动事件标记：受影响边高亮 + 中点脉冲圆点
  for (const [eid, ev] of eventEdges) {
    const e = edgeMap.get(eid)
    if (!e) continue
    const eOff = e.off ? Math.max(3.5, e.off * S) : 0
    const P = polyScreen(e, eOff, 0)
    ctx.strokeStyle = ev.color
    ctx.globalAlpha = 0.38
    ctx.lineWidth = Math.max(5, 3.2 * e.lanes * S + 3)
    tracePoly(ctx, P)
    ctx.globalAlpha = 1
    const mid = P[Math.floor(P.length / 2)]
    const pulse = 0.6 + 0.4 * Math.sin(t / 500)
    ctx.fillStyle = ev.color
    ctx.globalAlpha = pulse
    ctx.beginPath()
    ctx.arc(mid[0], mid[1], Math.max(3, 5 * S), 0, Math.PI * 2)
    ctx.fill()
    ctx.globalAlpha = 1
  }

  // 2) 路口节点
  for (const nd of nodes.value) {
    ctx.fillStyle = nd.tls ? c.accent : c.node
    ctx.globalAlpha = nd.tls ? 0.85 : 0.6
    ctx.beginPath()
    ctx.arc(X(nd.x), Y(nd.y), Math.max(2, 2.6 * S * 0.6), 0, Math.PI * 2)
    ctx.fill()
    ctx.globalAlpha = 1
  }

  // 3) 信号灯：逐 link（连接）一盏灯——同一车道可能有直行绿+转向红的混合状态，
  //    按 link 渲染才能如实反映"哪个方向能走"；同车道多 link 并排微偏移
  //    方向取道路自身末段方向（而非 偏移端点→路口中心，后者会因双向分离产生 ~19° 旋转偏差）
  const lightR = Math.max(2.6, 4.2 * Math.min(1.4, S))
  if (ui.settings.showLights) {
  for (const [tid, data] of tlsData) {
    const idx = tlsById.get(tid)
    if (idx === undefined) continue
    const nd = nodes.value[idx]
    const cx = X(nd.x), cy = Y(nd.y)
    const st = data.state_str || ''
    const links = data.links || []
    if (!links.length || !st) continue
    // 按（边, 车道）分桶，保留 link 序号用于并排偏移
    const byLane = new Map()
    for (let i = 0; i < links.length && i < st.length; i++) {
      const lk = links[i]
      const key = `${lk.from_edge}|${lk.from_lane || 0}`
      if (!byLane.has(key)) byLane.set(key, [])
      byLane.get(key).push({ edge: edgeMap.get(lk.from_edge), lane: lk.from_lane || 0, char: st[i] })
    }
    for (const arr of byLane.values()) {
      const e = arr[0].edge
      if (!e) continue
      // 用真实车道几何的端点定位灯（车道 0 已在真实几何上，无需公式偏移）
      const offPx = e.off ? Math.max(3.5, e.off * S) : 0
      const P = e.laneShapes && e.laneShapes[arr[0].lane]
        ? screenShape(e.laneShapes[arr[0].lane], offPx)
        : polyScreen(e, offPx, 0)
      let d0 = Math.hypot(P[0][0] - cx, P[0][1] - cy)
      let d1 = Math.hypot(P[P.length - 1][0] - cx, P[P.length - 1][1] - cy)
      const epIdx = d0 <= d1 ? 0 : P.length - 1
      const ep = P[epIdx]
      // 道路末段方向（指向路口）：沿道路自身，不受双向偏移影响
      const segA = epIdx === 0 ? P[1] : P[epIdx - 1]
      const rdx = ep[0] - segA[0], rdy = ep[1] - segA[1]
      const rl = Math.hypot(rdx, rdy) || 1
      const ux = rdx / rl, uy = rdy / rl
      const px = -uy, py = ux
      // 灯位：位于道路终点/起点（停车线处，远离路口中心）
      const back = -4.5 * Math.min(1.4, S)
      const subGap = Math.max(1.2, 3.6 * Math.min(1.4, S))
      for (let k = 0; k < arr.length; k++) {
        const laneOff = (k - (arr.length - 1) / 2) * subGap
        const lx = ep[0] + ux * back + px * laneOff
        const ly = ep[1] + uy * back + py * laneOff
        const col = stateColor(arr[k].char, c)
        ctx.fillStyle = col
        ctx.beginPath()
        ctx.arc(lx, ly, lightR, 0, Math.PI * 2)
        ctx.fill()
        ctx.strokeStyle = col
        ctx.globalAlpha = 0.35
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.arc(lx, ly, lightR + 2.4, 0, Math.PI * 2)
        ctx.stroke()
        ctx.globalAlpha = 1
      }
    }
  }
  } // end showLights

  // 4) 车辆：速度着色（停驶红 → 缓行琥珀 → 畅通绿），特殊类型用类型色
  //    朝向由屏幕空间位移方向计算（沿实际行驶方向），不依赖 SUMO angle
  const now = performance.now()
  if (ui.settings.showVehicles) {
  for (const v of vehicles.values()) {
    const k = Math.min(1, Math.max(0, (now - v.t0) / stepMs))
    const p = vehicleScreenPos(v, k)
    const size = 5.2 * Math.max(0.6, Math.min(1.4, S * 1.1))
    // 颜色：类型优先，否则按速度
    let col = TYPE_COLORS[v.type]
    if (!col) {
      const sp = v.speed ?? 0
      const r = Math.min(1, sp / MAX_SPEED)
      if (r < 0.05) col = c.red
      else if (r < 0.4) col = c.accent
      else col = c.green
    }
    ctx.save()
    ctx.translate(p.x, p.y)
    ctx.rotate(p.ang)
    ctx.fillStyle = col
    ctx.beginPath()
    if (typeof ctx.roundRect === 'function') {
      ctx.roundRect(-size * 0.7, -size * 0.35, size * 1.4, size * 0.7, size * 0.2)
    } else {
      ctx.rect(-size * 0.7, -size * 0.35, size * 1.4, size * 0.7)
    }
    ctx.fill()
    ctx.restore()
  }
  } // end showVehicles

  // 6) 选中高亮：车辆路线（虚线）/ 选中边 / 选中车辆描环
  if (selected.value) {
    if (selected.value.type === 'vehicle') {
      const route = selected.value.info?.route
      if (Array.isArray(route)) {
        ctx.setLineDash([6, 4])
        for (const rid of route) {
          const re = edgeMap.get(rid)
          if (!re) continue
          const rOff = re.off ? Math.max(3.5, re.off * S) : 0
          ctx.strokeStyle = c.accent
          ctx.globalAlpha = 0.5
          ctx.lineWidth = Math.max(4, 3.2 * S + 2)
          tracePoly(ctx, polyScreen(re, rOff, 0))
          ctx.globalAlpha = 1
        }
        ctx.setLineDash([])
      }
      const sv = vehicles.get(selected.value.id)
      if (sv) {
        const k = Math.min(1, Math.max(0, (now - sv.t0) / stepMs))
        const p = vehicleScreenPos(sv, k)
        ctx.strokeStyle = c.accent
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.arc(p.x, p.y, 10, 0, Math.PI * 2)
        ctx.stroke()
      }
    } else if (selected.value.type === 'node') {
      const sn = nodes.value.find((x) => x.id === selected.value.id)
      if (sn) {
        ctx.strokeStyle = c.accent
        ctx.globalAlpha = 0.9
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.arc(X(sn.x), Y(sn.y), Math.max(8, 9 * S), 0, Math.PI * 2)
        ctx.stroke()
        ctx.globalAlpha = 0.25
        ctx.fillStyle = c.accent
        ctx.beginPath()
        ctx.arc(X(sn.x), Y(sn.y), Math.max(6, 6 * S), 0, Math.PI * 2)
        ctx.fill()
        ctx.globalAlpha = 1
      }
    } else {
      const se = edgeMap.get(selected.value.id)
      if (se) {
        const sOff = se.off ? Math.max(3.5, se.off * S) : 0
        ctx.strokeStyle = c.accent
        ctx.globalAlpha = 0.45
        ctx.lineWidth = Math.max(5, 3.2 * se.lanes * S + 3)
        tracePoly(ctx, polyScreen(se, sOff, 0))
        ctx.globalAlpha = 1
      }
    }
  }

  // 7) 测试车辆：点选路线虚线高亮 + 白圈标记 + 到达统计
  if (ui.testMode && testRoute.value.length >= 2) {
    ctx.setLineDash([8, 5])
    ctx.strokeStyle = '#ffffff'
    ctx.globalAlpha = 0.7
    ctx.lineWidth = Math.max(3, 2.5 * S + 1)
    for (const rid of testRoute.value) {
      const re = edgeMap.get(rid)
      if (!re) continue
      const rOff = re.off ? Math.max(3.5, re.off * S) : 0
      tracePoly(ctx, polyScreen(re, rOff, 0))
    }
    ctx.setLineDash([])
    ctx.globalAlpha = 1
  }
  if (testVid.value) {
    const tv = vehicles.get(testVid.value)
    if (tv) {
      const k = Math.min(1, Math.max(0, (now - tv.t0) / stepMs))
      const p = vehicleScreenPos(tv, k)
      const pulse = 0.5 + 0.5 * Math.sin(t / 300)
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 2.5
      ctx.globalAlpha = pulse
      ctx.beginPath()
      ctx.arc(p.x, p.y, 11, 0, Math.PI * 2)
      ctx.stroke()
      ctx.globalAlpha = 1
      ctx.fillStyle = '#ffffff'
      ctx.font = `bold ${Math.max(9, 10 * S)}px var(--font-sans)`
      ctx.textAlign = 'center'
      ctx.fillText('T', p.x, p.y - 13)
    }
  }
}

function loop(t) { draw(t); raf = requestAnimationFrame(loop) }

// ── 交互 ──────────────────────────────────────────────────
function onWheel(ev) {
  ev.preventDefault()
  const el = canvas.value
  const rect = el.getBoundingClientRect()
  const mx = ev.clientX - rect.left, my = ev.clientY - rect.top
  const f = ev.deltaY < 0 ? 1.12 : 1 / 1.12
  const ns = Math.min(400, Math.max(0.005, view.scale * f))
  const k = ns / view.scale
  view.tx = mx - (mx - view.tx) * k
  view.ty = my - (my - view.ty) * k
  view.scale = ns
}
let dragging = false, lastX = 0, lastY = 0, downX = 0, downY = 0
let hoverCursor = false

function onDown(ev) {
  dragging = true
  lastX = downX = ev.clientX
  lastY = downY = ev.clientY
}
function onMove(ev) {
  const rect = canvas.value.getBoundingClientRect()
  const mx = ev.clientX - rect.left, my = ev.clientY - rect.top
  if (dragging) {
    view.tx += ev.clientX - lastX; view.ty += ev.clientY - lastY
    lastX = ev.clientX; lastY = ev.clientY
    return
  }
  // 悬停：命中车辆/道路 → 指针样式
  const hit = hitTest(mx, my)
  const want = !!hit
  if (want !== hoverCursor) {
    hoverCursor = want
    canvas.value.style.cursor = want ? 'pointer' : 'grab'
  }
}
function onUp(ev) {
  dragging = false
  if (Math.hypot(ev.clientX - downX, ev.clientY - downY) < 4) {
    handleClick(ev)
  }
}
function onDblClick() {
  if (ui.settings.dblClickReset) fitView()
}

// ── 点击选中（车辆/道路）──────────────────────────────────
const selected = ref(null)   // {type, id, info}
const addCount = ref(20)
const vehType = ref('DEFAULT_VEHTYPE')
const infoMsg = ref('')
let infoTimer = null

const VEH_TYPES = [
  { value: 'DEFAULT_VEHTYPE', label: '小汽车' },
  { value: 'bus', label: '公交车' },
  { value: 'truck', label: '货车' },
  { value: 'bicycle', label: '自行车' },
  { value: 'fleet', label: '车队车辆' },
]

function distToSeg(px, py, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1]
  const L2 = dx * dx + dy * dy || 1
  let t = ((px - a[0]) * dx + (py - a[1]) * dy) / L2
  t = Math.max(0, Math.min(1, t))
  return Math.hypot(px - (a[0] + dx * t), py - (a[1] + dy * t))
}

/** 车辆屏幕绘制位置（与 draw 完全一致：插值 + 双向偏移 + 航向），供命中检测/选中圈复用 */
function vehicleScreenPos(v, k) {
  const x = v.px + (v.x - v.px) * k
  const y = v.py + (v.y - v.py) * k
  const mx = X(v.x) - X(v.px)
  const my = Y(v.y) - Y(v.py)
  if (Math.hypot(mx, my) > 1e-6) v.heading = Math.atan2(my, mx)
  const ang = v.heading ?? 0
  let shift = 0
  if (v.lane) {
    const lp = v.lane.split('_')
    lp.pop()
    const e = edgeMap.get(lp.join('_'))
    if (e && e.off) shift = Math.max(3.5, e.off * view.scale)
  }
  return { x: X(x) - Math.sin(ang) * shift, y: Y(y) + Math.cos(ang) * shift, ang }
}

function hitTest(mx, my) {
  const now = performance.now()
  // 车辆（与绘制位置一致：插值 + 双向偏移）；命中半径 14px（车身约 5px，留足容错）
  for (const v of vehicles.values()) {
    const k = Math.min(1, Math.max(0, (now - v.t0) / stepMs))
    const p = vehicleScreenPos(v, k)
    if (Math.hypot(p.x - mx, p.y - my) < 14) return { type: 'vehicle', id: v.id }
  }
  // 道路（原始中心线，容差 12px）
  let best = null
  for (const e of edges.value) {
    const P = e.pts.map(([x, y]) => [X(x), Y(y)])
    for (let i = 0; i < P.length - 1; i++) {
      const d = distToSeg(mx, my, P[i], P[i + 1])
      if (d < 12 && (!best || d < best.d)) best = { type: 'edge', id: e.id, d }
    }
  }
  return best ? { type: 'edge', id: best.id } : null
}

async function handleClick(ev) {
  const rect = canvas.value.getBoundingClientRect()
  const mx = ev.clientX - rect.left, my = ev.clientY - rect.top
  const hit = hitTest(mx, my)
  if (ui.testMode) {
    // 测试车辆模式：点击道路选择路线（再点已选边 = 取消该段）
    if (hit?.type === 'edge') {
      const id = hit.id
      const i = testRoute.value.indexOf(id)
      if (i >= 0) testRoute.value.splice(i, 1)
      else testRoute.value.push(id)
    }
    return
  }
  if (!hit) { selected.value = null; return }
  selected.value = { ...hit, info: null, x: ev.clientX - rect.left, y: ev.clientY - rect.top }
  await refreshInfo()
}

// ── 测试车辆（单车，点选路线，走完统计等待） ────────────────
const testRoute = ref([])     // 点选的边序列（起点…终点）
const testVid = ref(null)
const testStatus = ref(null)  // {arrived, total_wait, max_wait, per_edge, route}
let testTimer = null

async function startTestVehicle() {
  const r = testRoute.value
  if (r.length < 2) return
  try {
    const d = await apiPost('/test-vehicle/start', {
      from_edge: r[0], to_edge: r[r.length - 1], via: r.slice(1, -1) })
    testVid.value = d.vid
    testStatus.value = { active: true, route: d.route, arrived: false }
    pollTest()
  } catch (e) {
    infoMsg.value = `测试车辆启动失败: ${e.message}`
  }
}

async function pollTest() {
  clearInterval(testTimer)
  testTimer = setInterval(async () => {
    try {
      const s = await apiGet('/test-vehicle/status')
      testStatus.value = s
      if (s.arrived) clearInterval(testTimer)
    } catch { /* 后端未起 */ }
  }, 2000)
}

function clearTest() {
  clearInterval(testTimer)
  testRoute.value = []
  testVid.value = null
  testStatus.value = null
  ui.setTestMode(false)
}

function undoTest() { testRoute.value.pop() }

async function refreshInfo() {
  const s = selected.value
  if (!s) return
  try {
    if (s.type === 'vehicle') {
      s.info = await apiGet(`/vehicles/${s.id}`)
    } else if (s.type === 'node') {
      // 路口信息直接取实时路口指标（每步 WS 推送）
      s.info = { ...(metrics.perTls[s.id] || {}), id: s.id }
    } else {
      s.info = await apiGet(`/metrics/edge/${s.id}`)
    }
  } catch (e) {
    s.info = { error: e.message }
  }
}

/** 将视图中心移动到对象位置并保证一定放大（供自定义指标定位） */
function focusOn(type, id) {
  let wx, wy
  if (type === 'vehicle') {
    const v = vehicles.get(id)
    if (v) { wx = v.x; wy = v.y }
  } else if (type === 'edge') {
    const e = edgeMap.get(id)
    if (e && e.pts.length) { const m = e.pts[Math.floor(e.pts.length / 2)]; wx = m[0]; wy = m[1] }
  } else if (type === 'node') {
    const n = nodes.value.find((x) => x.id === id)
    if (n) { wx = n.x; wy = n.y }
  }
  if (wx === undefined || !canvas.value) return
  const W = canvas.value.clientWidth, H = canvas.value.clientHeight
  view.scale = Math.max(view.scale, Math.min(W, H) / 360)
  view.tx = W / 2 - wx * view.scale
  view.ty = H / 2 + wy * view.scale // Y 翻转：北朝上
}

// 自定义指标点击 → 聚焦选中（来自实时指标栏）
watch(() => ui.spotlight, async (sp) => {
  if (!sp) return
  selected.value = { type: sp.type, id: sp.id, info: null, x: 60, y: 60 }
  focusOn(sp.type, sp.id)
  await refreshInfo()
})

async function addTrafficOnEdge() {
  if (selected.value?.type !== 'edge') return
  const id = selected.value.id
  try {
    await apiPost('/events/inject', {
      event_type: 'large_event',
      params: { edge_ids: [id], vehicles: addCount.value, veh_type: vehType.value } })
    events.refresh() // 同步事件列表 → 画布高亮受影响边
    infoMsg.value = `已向 ${id} 加入 ${addCount.value} 辆车`
    await refreshInfo()
  } catch (e) {
    infoMsg.value = `失败: ${e.message}`
  }
}

watch([() => selected.value?.id, () => ui.settings.infoAutoRefresh], () => {
  clearInterval(infoTimer)
  if (selected.value && ui.settings.infoAutoRefresh) {
    infoTimer = setInterval(refreshInfo, 4000)
  }
})

// ── 生命周期 ──────────────────────────────────────────────
watch(() => sim.status, (s) => {
  if (s === 'running') { vehicles.clear(); tlsData.clear(); loadNetwork() }
  if (s === 'idle') { clearNet(); hint.value = '请先启动仿真以加载路网' }
})
onMounted(() => {
  refreshColors()
  unsubs = [
    subscribe('vehicle_update', handleVehicles),
    subscribe('tls_update', handleTls),
  ]
  raf = requestAnimationFrame(loop)
  window.addEventListener('resize', fitView)
  // 仅在已有运行会话时加载路网；新打开页面一律空白
  //（后端残留会话由 App 挂载时自动停止并清空）
  if (sim.status === 'running') loadNetwork()
})
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  clearInterval(infoTimer)
  clearInterval(testTimer)
  unsubs.forEach((fn) => fn())
  window.removeEventListener('resize', fitView)
})
</script>

<template>
  <div class="canvas-wrap">
    <canvas
      ref="canvas" class="net-canvas"
      @wheel="onWheel" @mousedown="onDown" @mousemove="onMove"
      @mouseup="onUp" @mouseleave="onUp" @dblclick="onDblClick"
    />
    <div v-if="hint" class="overlay">{{ hint }}</div>
    <div v-else class="corner">
      <span class="corner-name">{{ netName }}</span>
      <span v-if="netFile" class="mono corner-file">{{ netFile }}</span>
      <!-- 扰动注入图例（设置中可开关） -->
      <div v-if="ui.settings.showLegend" class="legend ev">
        <span class="lg"><i class="line" style="background:#ff6b6b" />事故</span>
        <span class="lg"><i class="line" style="background:#b197fc" />施工</span>
        <span class="lg"><i class="line" style="background:#4ecdc4" />突发车流</span>
      </div>
      <span class="mono corner-meta">{{ edges.length }} 边 · {{ nodes.length }} 节点 · {{ vehicles.size }} 车辆</span>
      <div class="legend">
        <span class="lg"><i class="sw red" />停驶</span>
        <span class="lg"><i class="sw amber" />缓行</span>
        <span class="lg"><i class="sw green" />畅通</span>
      </div>
    </div>
    <div class="canvas-toolbar">
      <span>{{ ui.testMode ? '测试车辆选路：点击道路加入路线（再点已选边取消）' : '滚轮缩放 · 拖拽平移 · 双击复位 · 点击车辆/道路查看详情' }}</span>
    </div>

    <!-- 测试车辆控制面板 -->
    <div v-if="ui.testMode || testVid" class="test-panel">
      <div class="test-head">
        <span class="test-title">测试车辆</span>
        <button class="test-close" @click="clearTest">×</button>
      </div>
      <template v-if="testStatus?.arrived">
        <div class="kv"><span>状态</span><span class="mono" style="color:var(--signal-green)">已到达</span></div>
        <div class="kv"><span>总等待</span><span class="mono">{{ testStatus.total_wait }} s</span></div>
        <div class="kv"><span>单步最大等待</span><span class="mono">{{ testStatus.max_wait }} s</span></div>
        <div class="kv route"><span>沿途等待</span><span class="mono route-list">{{ Object.entries(testStatus.per_edge || {}).map(([e, w]) => `${e}:${w}s`).join(' · ') || '—' }}</span></div>
      </template>
      <template v-else-if="testVid">
        <div class="kv"><span>状态</span><span class="mono" style="color:var(--accent)">行驶中…</span></div>
        <div class="kv route"><span>路线</span><span class="mono route-list">{{ (testStatus?.route || testRoute).join(' → ') }}</span></div>
      </template>
      <template v-else>
        <div class="kv"><span>已选边</span><span class="mono route-list">{{ testRoute.length ? testRoute.join(' → ') : '（点击道路选择，≥2 条）' }}</span></div>
        <div class="test-actions">
          <button class="test-btn" :disabled="testRoute.length < 2" @click="startTestVehicle">开始</button>
          <button class="test-btn" :disabled="!testRoute.length" @click="undoTest">撤销</button>
          <button class="test-btn" @click="testRoute = []">清空</button>
        </div>
      </template>
    </div>

    <!-- 选中信息卡 -->
    <div v-if="selected" class="info-card"
      :style="{ left: Math.min(selected.x, 40) + 'px', top: Math.min(selected.y, 40) + 'px' }">
      <div class="info-head">
        <span class="mono info-id">{{ selected.id }}</span>
        <button class="info-close" @click="selected = null">×</button>
      </div>
      <template v-if="selected.info?.error">
        <div class="mono info-err">{{ selected.info.error }}</div>
      </template>
      <template v-else-if="selected.type === 'vehicle' && selected.info">
        <div class="kv"><span>类型</span><span class="mono">{{ VEH_TYPE_LABELS[selected.info.type] || selected.info.type || '—' }}</span></div>
        <div class="kv"><span>速度</span><span class="mono">{{ ((selected.info.speed ?? 0) * 3.6).toFixed(1) }} km/h</span></div>
        <div class="kv"><span>车道</span><span class="mono">{{ selected.info.lane ?? '—' }}</span></div>
        <div class="kv"><span>累计等待</span><span class="mono">{{ (selected.info.waiting_time ?? 0).toFixed(1) }} s</span></div>
        <div class="kv route"><span>路线</span><span class="mono route-list">{{ (selected.info.route || []).join(' → ') || '—' }}</span></div>
      </template>
      <template v-else-if="selected.type === 'node' && selected.info">
        <div class="kv"><span>排队车辆</span><span class="mono">{{ selected.info.queue_length ?? 0 }} 辆</span></div>
        <div class="kv"><span>平均等待</span><span class="mono">{{ (selected.info.waiting_time ?? 0).toFixed(1) }} s</span></div>
        <div class="kv"><span>通过车辆</span><span class="mono">{{ selected.info.throughput ?? 0 }}</span></div>
        <div class="kv"><span>当前相位</span><span class="mono">{{ selected.info.current_phase ?? '—' }} · 时长 {{ selected.info.phase_duration ?? '—' }}s</span></div>
      </template>
      <template v-else-if="selected.info">
        <div class="kv"><span>车道数</span><span class="mono">{{ edgeMap.get(selected.id)?.lanes ?? '—' }}</span></div>
        <div class="kv"><span>限速</span><span class="mono">{{ ((selected.info.speed_limit ?? 0) * 3.6).toFixed(1) }} km/h</span></div>
        <div class="kv"><span>在网车辆</span><span class="mono">{{ selected.info.vehicle_count }}</span></div>
        <div class="kv"><span>平均速度</span><span class="mono">{{ ((selected.info.mean_speed ?? 0) * 3.6).toFixed(1) }} km/h</span></div>
        <div class="kv"><span>占有率</span><span class="mono">{{ (selected.info.occupancy * 100).toFixed(1) }}%</span></div>
        <div class="kv"><span>通行时间</span><span class="mono">{{ selected.info.travel_time ?? '—' }} s</span></div>
        <div class="add-row">
          <input v-model.number="addCount" type="number" min="1" max="200" class="add-inp num" />
          <select v-model="vehType" class="add-inp" title="车辆类型">
            <option v-for="t in VEH_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
          <button class="add-btn" @click="addTrafficOnEdge">在此边添加车流</button>
        </div>
        <div v-if="infoMsg" class="mono info-msg">{{ infoMsg }}</div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.canvas-wrap { position: relative; flex: 1; min-width: 0; background: var(--canvas-bg); overflow: hidden; }
.net-canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; cursor: grab; }
.net-canvas:active { cursor: grabbing; }
.overlay {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--text-3); font-size: 13px; pointer-events: none;
}
.corner {
  position: absolute; top: var(--space-3); left: var(--space-3);
  display: flex; flex-direction: column; gap: 3px;
  padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-ctrl);
  background: var(--bg-panel);
}
.corner-name { font-size: 12px; color: var(--text-1); }
.corner-file { font-size: 10px; color: var(--text-3); }
.corner-meta { font-size: 10px; color: var(--text-3); }
.legend { display: flex; gap: 8px; font-size: 10px; color: var(--text-3); }
.legend.ev { padding-top: 2px; border-top: 1px dashed var(--border); }
.lg { display: inline-flex; align-items: center; gap: 4px; }
.sw { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.sw.red { background: var(--signal-red); }
.sw.amber { background: var(--accent); }
.sw.green { background: var(--signal-green); }
.lg .line { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
.canvas-toolbar {
  position: absolute; bottom: var(--space-3); left: 50%; transform: translateX(-50%);
  padding: 4px 12px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--bg-panel); font-size: 11px; color: var(--text-3); pointer-events: none;
}
.info-card {
  position: absolute; z-index: 5; width: 260px;
  padding: var(--space-3); border: 1px solid var(--border-strong); border-radius: var(--radius-panel);
  background: var(--bg-panel); box-shadow: var(--shadow-2);
  font-size: 12px;
}
.test-panel {
  position: absolute; z-index: 5; left: var(--space-3); bottom: 44px; width: 260px;
  padding: var(--space-3); border: 1px solid var(--border-strong); border-radius: var(--radius-panel);
  background: var(--bg-panel); box-shadow: var(--shadow-2); font-size: 12px;
}
.test-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2); }
.test-title { font-size: 13px; font-weight: 700; color: #fff; }
.test-close { border: none; background: none; color: var(--text-3); font-size: 14px; cursor: pointer; }
.test-close:hover { color: var(--signal-red); }
.test-actions { display: flex; gap: 6px; margin-top: var(--space-2); }
.test-btn {
  flex: 1; height: 24px; border: 1px solid var(--border-strong); border-radius: var(--radius-ctrl);
  background: var(--bg-elev); color: var(--text-1); font-size: 11px; cursor: pointer; white-space: nowrap;
}
.test-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.test-btn:first-child { border-color: #fff; color: #fff; }
.info-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2); }
.info-id { font-size: 13px; font-weight: 700; color: var(--accent); }
.info-close {
  border: none; background: none; color: var(--text-3); font-size: 14px; cursor: pointer; padding: 0 2px;
}
.info-close:hover { color: var(--signal-red); }
.kv { display: flex; justify-content: space-between; gap: 8px; padding: 2px 0; color: var(--text-2); }
.kv > span:first-child { color: var(--text-3); }
.route-list { max-width: 170px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.route .route-list:hover { white-space: normal; overflow: visible; }
.info-err { color: var(--signal-red); font-size: 11px; }
.add-row { display: flex; gap: 6px; margin-top: var(--space-2); }
.add-inp { width: 60px; height: 24px; padding: 0 6px; background: var(--bg-elev); color: var(--text-1); border: 1px solid var(--border); border-radius: var(--radius-ctrl); }
.add-btn {
  flex: 1; height: 24px; border: 1px solid var(--accent); border-radius: var(--radius-ctrl);
  background: var(--accent-soft); color: var(--accent); font-size: 11px; cursor: pointer;
}
.add-btn:hover { background: var(--accent); color: oklch(0.16 0.01 80); }
.info-msg { color: var(--signal-green); font-size: 11px; margin-top: 4px; }
</style>
