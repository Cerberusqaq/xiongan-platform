<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import TopBar from './components/TopBar.vue'
import NetCanvas from './components/NetCanvas.vue'
import AgentPanel from './components/AgentPanel.vue'
import MetricsPanel from './components/MetricsPanel.vue'
import SchemePanel from './components/SchemePanel.vue'
import EventPanel from './components/EventPanel.vue'
import CompareSection from './components/CompareSection.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import { useUiStore } from './stores/ui'
import { useSimStore } from './stores/sim'
import { useAgentStore } from './stores/agent'
import { useMetricsStore } from './stores/metrics'
import { initRealtime, subscribe } from './realtime'

const ui = useUiStore()
const sim = useSimStore()
const agent = useAgentStore()
const metrics = useMetricsStore()

const settingsOpen = ref(false)

// ── 左栏单栏切换模式（tabs）：一次只显示一个子栏 ────────────
const LEFT_TABS = [
  { key: 'metrics', label: '指标' },
  { key: 'scheme', label: '方案' },
  { key: 'event', label: '事件' },
]
const leftTabs = computed(() => ui.viewMode === 'pro'
  ? LEFT_TABS
  : LEFT_TABS.filter((t) => t.key === 'metrics'))
const leftTab = computed(() => {
  const t = ui.settings.leftTab
  return leftTabs.value.some((x) => x.key === t) ? t : 'metrics'
})

let timers = []
let drag = null

onMounted(async () => {
  ui.apply()
  initRealtime()

  subscribe('metrics_update', (d) => metrics.applyWs(d))
  subscribe('simulation_step', (d) => { sim.applyStep(d); metrics.applyStep(d) })

  sim.listNetworks()
  agent.fetchStatus()
  metrics.refresh()

  // 新打开页面：若后端残留上一会话（上次关页面前没停止），自动清空，
  // 保证打开即是全新空白，不默认回到上次的路网
  await sim.refreshStatus()
  if (sim.status !== 'idle') {
    try { await sim.stop(); metrics.resetSession() } catch { sim.status = 'idle'; sim.sessionId = null; metrics.resetSession() }
  }

  timers.push(setInterval(() => sim.refreshStatus(), 3000))
  timers.push(setInterval(() => { if (sim.status !== 'idle') metrics.refresh() }, 5000))
  timers.push(setInterval(() => { if (ui.viewMode === 'pro' && sim.status !== 'idle') metrics.loadHistory('avg_speed') }, 15000))
})
onBeforeUnmount(() => timers.forEach(clearInterval))

// ── 面板拖拽调整（左右栏宽 / 上下区高） ─────────────────────
// 关键：拖拽开始时快照各面板初始值，位移从快照计算——
// 若把"全量位移"加到已更新的当前值上会叠加放大（越拖越灵敏）
const SENSITIVITY = 1

function startDrag(kind, ev) {
  ev.preventDefault()
  drag = {
    kind,
    startX: ev.clientX,
    startY: ev.clientY,
    snap: {
      leftW: ui.leftW, rightW: ui.rightW, bottomH: ui.bottomH,
      metricsH: ui.metricsH, schemeH: ui.schemeH,
    },
  }
  document.body.style.userSelect = 'none'
  document.body.style.cursor = kind === 'bottom' ? 'row-resize' : 'col-resize'
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}
function onDragMove(e) {
  if (!drag) return
  const dx = (e.clientX - drag.startX) * SENSITIVITY
  const dy = (e.clientY - drag.startY) * SENSITIVITY
  if (drag.kind === 'left') ui.setLeftW(drag.snap.leftW + dx)
  else if (drag.kind === 'right') ui.setRightW(drag.snap.rightW - dx)
  else if (drag.kind === 'bottom') ui.setBottomH(drag.snap.bottomH - dy)
  else if (drag.kind === 'metrics') ui.setMetricsH(drag.snap.metricsH + dy)
  else if (drag.kind === 'scheme') ui.setSchemeH(drag.snap.schemeH + dy)
}
function onDragEnd() {
  drag = null
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
}
function resetPanel(kind) {
  if (kind === 'left') ui.setLeftW(300)
  else if (kind === 'right') ui.setRightW(380)
  else if (kind === 'bottom') ui.setBottomH(240)
  else if (kind === 'metrics') ui.setMetricsH(210)
  else if (kind === 'scheme') ui.setSchemeH(330)
}

function handleStart({ net, routes, addFiles, scheme }) {
  sim.start({
    netPath: net.net_path,
    routes,
    addFiles,
    scheme: scheme || 'scheme_2',
    schemeParams: { mode: 'auto', mappo_weights: 'models/weights/mappo_act_full' },
  }).catch((e) => console.warn('[start] 启动失败:', e.message))
}
function handleStop() { sim.stop().then(() => metrics.resetSession()).catch(() => {}) }
function handlePause() { sim.pause().catch(() => {}) }
function handleResume() { sim.resume().catch(() => {}) }
function handleSpeed(v) { sim.setSpeed(v).catch(() => {}) }
</script>

<template>
  <div class="shell">
    <TopBar
      :busy="sim.starting"
      @start="handleStart" @stop="handleStop" @pause="handlePause" @resume="handleResume"
      @speed="handleSpeed"
      @toggle-theme="ui.toggleTheme" @toggle-view="ui.setViewMode(ui.viewMode === 'pro' ? 'normal' : 'pro')"
      @open-settings="settingsOpen = true"
    />

    <main class="layout">
      <aside class="left" :style="{ width: ui.leftW + 'px' }">
        <!-- 模式一：堆叠（默认）——三个子栏同时显示 -->
        <template v-if="ui.settings.leftMode === 'stacked'">
          <MetricsPanel :style="{ height: ui.metricsH + 'px' }" />
          <template v-if="ui.viewMode === 'pro'">
            <div class="h-handle" title="拖拽调整指标区高度（双击复位）"
              @mousedown="startDrag('metrics', $event)" @dblclick="resetPanel('metrics')" />
            <SchemePanel :style="{ height: ui.schemeH + 'px' }" />
            <div class="h-handle" title="拖拽调整方案区高度（双击复位）"
              @mousedown="startDrag('scheme', $event)" @dblclick="resetPanel('scheme')" />
            <EventPanel class="left-rest" />
          </template>
        </template>

        <!-- 模式二：单栏切换——通过页签一次只显示一个子栏 -->
        <template v-else>
          <div class="left-tabs">
            <button v-for="t in leftTabs" :key="t.key" class="ltab"
              :class="{ on: leftTab === t.key }"
              @click="ui.setSetting('leftTab', t.key)">{{ t.label }}</button>
          </div>
          <MetricsPanel v-show="leftTab === 'metrics'" class="left-rest" />
          <SchemePanel v-if="ui.viewMode === 'pro'" v-show="leftTab === 'scheme'" class="left-rest" />
          <EventPanel v-if="ui.viewMode === 'pro'" v-show="leftTab === 'event'" class="left-rest" />
        </template>
      </aside>

      <div class="v-handle" title="拖拽调整左栏宽度（双击复位）"
        @mousedown="startDrag('left', $event)" @dblclick="resetPanel('left')" />

      <NetCanvas class="center" />

      <div class="v-handle" title="拖拽调整右栏宽度（双击复位）"
        @mousedown="startDrag('right', $event)" @dblclick="resetPanel('right')" />

      <aside class="right" :style="{ width: ui.rightW + 'px' }">
        <AgentPanel />
      </aside>
    </main>

    <template v-if="ui.viewMode === 'pro'">
      <div class="h-handle" title="拖拽调整对比区高度（双击复位）"
        @mousedown="startDrag('bottom', $event)" @dblclick="resetPanel('bottom')" />
      <CompareSection :height="ui.bottomH" />
    </template>

    <SettingsPanel :open="settingsOpen" @close="settingsOpen = false" />
  </div>
</template>

<style scoped>
.shell { display: flex; flex-direction: column; height: 100%; }
.layout { flex: 1; min-height: 0; display: flex; }
.left {
  display: flex; flex-direction: column; gap: var(--space-3);
  padding: var(--space-3); overflow: hidden;
}
.left-rest { flex: 1; min-height: 0; }
.left-tabs {
  display: flex; gap: 4px; flex: 0 0 auto;
  padding: 3px; border: 1px solid var(--border);
  border-radius: var(--radius-ctrl); background: var(--bg-elev);
}
.ltab {
  flex: 1; height: 24px; border: none; border-radius: var(--radius-ctrl);
  background: transparent; color: var(--text-2); font-size: 12px; cursor: pointer;
}
.ltab:hover { color: var(--text-1); }
.ltab.on { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.center { flex: 1; min-width: 0; }
.right { padding: var(--space-3); overflow: hidden; }

/* 拖拽手柄 */
.v-handle {
  flex: 0 0 5px; margin: 0 -1px; cursor: col-resize;
  background: transparent; border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  transition: background var(--dur-fast);
}
.v-handle:hover, .v-handle:active { background: var(--accent-soft); }
.h-handle {
  flex: 0 0 7px; cursor: row-resize;
  background: transparent; border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  position: relative;
  transition: background var(--dur-fast);
}
.h-handle::after {
  content: ''; position: absolute; left: 50%; top: 2px; transform: translateX(-50%);
  width: 36px; height: 3px; border-radius: 2px; background: var(--border-strong);
}
.h-handle:hover::after, .h-handle:active::after { background: var(--accent); }
.h-handle:hover, .h-handle:active { background: var(--accent-soft); }
</style>
