<script setup>
import { computed, ref, watch } from 'vue'
import AppButton from './ui/AppButton.vue'
import { useSimStore } from '../stores/sim'
import { useUiStore } from '../stores/ui'
import { apiGet, apiUpload } from '../api/http'

defineProps({ busy: { type: Boolean, default: false } })
const emit = defineEmits(['start', 'stop', 'pause', 'resume', 'speed', 'toggle-view', 'open-settings'])

const sim = useSimStore()
const ui = useUiStore()

const speed = ref(1)
const selected = ref('')
const scheme = ref('scheme_2')
const fileInput = ref(null)

// 路网下拉：中文名 + 悬停预览
const ddOpen = ref(false)
const hoverName = ref('')
const hoverSvg = ref('')
watch(hoverName, async (name) => {
  if (!name) { hoverSvg.value = ''; return }
  try { hoverSvg.value = await apiGet(`/networks/preview?name=${encodeURIComponent(name)}`) } catch { hoverSvg.value = '' }
})
// 下拉关闭时（点击选中/再次点击按钮）清空悬停预览，避免残留小图
watch(ddOpen, (open) => { if (!open) { hoverName.value = ''; hoverSvg.value = '' } })
const currentNet = computed(() => sim.nets.find((n) => n.net_path === selected.value))

const SCHEMES = [
  { value: 'scheme_1', label: '方案一 · 固定配时+绿波' },
  { value: 'scheme_2', label: '方案二 · MAPPO/SCOOT' },
  { value: 'scheme_3', label: '方案三 · 车端引导' },
  { value: 'none', label: '基线 · 固定配时' },
]

const netOptions = computed(() => sim.nets)

const statusMeta = computed(() => ({
  running: { label: '运行中', cls: 'run' },
  paused: { label: '已暂停', cls: 'pause' },
  idle: { label: '未启动', cls: 'idle' },
}[sim.status] || { label: '未启动', cls: 'idle' }))

function pickDefault(net) {
  const routes = net.routes || []
  const adds = net.adds || []
  const match = (arr, re) => arr.find((p) => re.test(p)) || arr[0] || ''
  const route = match(routes, /routes_clean700|traffic_med/)
  const add = match(adds, /timing_safe/)
  return { routes: route ? [route] : [], addFiles: add ? [add] : [] }
}

function onStart() {
  const net = sim.nets.find((n) => n.net_path === selected.value)
  if (!net) return
  emit('start', { net, scheme: scheme.value, scenario: ui.scenario, ...pickDefault(net) })
}

async function onUpload(ev) {
  const files = Array.from(ev.target.files || [])
  ev.target.value = ''
  if (!files.length) return
  try {
    await apiUpload('/networks/upload', files)
    await sim.listNetworks()
    const custom = sim.nets.filter((n) => n.name.startsWith('custom/'))
    if (custom.length) selected.value = custom[custom.length - 1].net_path
  } catch (e) {
    console.warn('[upload]', e.message)
  }
}
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <span class="brand-dot" />
      <span class="brand-name">车路云协同管控平台</span>
    </div>

    <div class="group">
      <div class="net-dd">
        <button class="ctrl net-btn" @click="ddOpen = !ddOpen" title="路网选择（悬停列表项可预览）">
          {{ currentNet?.label || currentNet?.name || '选择路网…' }} ▾
        </button>
        <div v-if="ddOpen" class="dd" @mouseleave="hoverName = ''">
          <div v-if="sim.nets.some((n) => n.name.startsWith('custom/'))" class="dd-group">自定义上传</div>
          <div v-for="n in sim.nets.filter((x) => x.name.startsWith('custom/'))" :key="n.net_path"
            class="dd-item" :class="{ cur: n.net_path === selected }"
            @mouseenter="hoverName = n.name"
            @click="selected = n.net_path; ddOpen = false">{{ n.label || n.name }}</div>
          <div class="dd-group">内置路网</div>
          <div v-for="n in sim.nets.filter((x) => !x.name.startsWith('custom/'))" :key="n.net_path"
            class="dd-item" :class="{ cur: n.net_path === selected }"
            @mouseenter="hoverName = n.name"
            @click="selected = n.net_path; ddOpen = false">{{ n.label || n.name }}</div>
        </div>
        <div v-if="hoverName && hoverSvg" class="dd-preview">
          <img :src="'data:image/svg+xml;utf8,' + encodeURIComponent(hoverSvg)" alt="路网预览" />
          <div class="dd-preview-name mono">{{ hoverName }}</div>
        </div>
      </div>
      <AppButton @click="fileInput.click()" title="上传 SUMO 路网文件（.net.xml + .rou.xml + .add.xml）">上传路网</AppButton>
      <input ref="fileInput" type="file" multiple accept=".xml" hidden @change="onUpload" />
      <select v-model="scheme" class="ctrl" :disabled="sim.status !== 'idle'" title="控制方案">
        <option v-for="s in SCHEMES" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
      <AppButton variant="primary" class="ic-btn" :disabled="!selected || sim.status !== 'idle' || busy"
        @click="onStart" :title="busy ? '启动中…' : '启动仿真'">
        <svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.6v10.8l9.2-5.4z"/></svg>
      </AppButton>
      <AppButton class="ic-btn" variant="danger" :disabled="sim.status === 'idle' || busy"
        @click="emit('stop')" title="停止">
        <svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><rect x="3.4" y="3.4" width="9.2" height="9.2" rx="1.4"/></svg>
      </AppButton>
      <AppButton class="ic-btn" :disabled="sim.status !== 'running'" @click="emit('pause')" title="暂停">
        <svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><rect x="3.4" y="2.4" width="3.4" height="11.2" rx="0.9"/><rect x="9.2" y="2.4" width="3.4" height="11.2" rx="0.9"/></svg>
      </AppButton>
      <AppButton class="ic-btn" variant="success" :disabled="sim.status !== 'paused'" @click="emit('resume')" title="恢复">
        <svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.6v10.8l9.2-5.4z"/></svg>
      </AppButton>
      <select v-model="speed" class="ctrl" :disabled="sim.status === 'idle'" @change="emit('speed', Number(speed))">
        <option :value="1">1×</option><option :value="2">2×</option><option :value="5">5×</option>
      </select>
    </div>

    <div class="group right">
      <span class="sim-chip" :class="statusMeta.cls">
        <i class="dot" />
        <span>{{ statusMeta.label }}</span>
        <span v-if="sim.status !== 'idle'" class="mono step">步 {{ sim.step }} · {{ Math.floor(sim.simTime / 60) }}:{{ String(sim.simTime % 60).padStart(2, '0') }}</span>
      </span>
      <AppButton @click="emit('open-settings')" title="设置">设置</AppButton>
      <AppButton :variant="ui.viewMode === 'normal' ? 'primary' : 'success'" @click="emit('toggle-view')"
        :title="ui.viewMode === 'normal' ? '切换到专业模式' : '切换到普通模式'">
        {{ ui.viewMode === 'normal' ? '普通模式' : '专业模式' }}
      </AppButton>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  min-height: var(--topbar-h);
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-4);
  padding: 6px var(--space-4);
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: var(--space-2); flex: 0 0 auto; }
.brand-dot {
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--accent); box-shadow: var(--glow-accent);
}
.brand-name { font-size: 14px; font-weight: 700; letter-spacing: 0.03em; }
.group { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.group.right { margin-left: auto; flex: 0 0 auto; }
.ctrl {
  height: 28px; padding: 0 8px; max-width: 220px;
  background: var(--bg-elev); color: var(--text-1);
  border: 1px solid var(--border); border-radius: var(--radius-ctrl);
  font-size: 12px;
}
/* 播放/停止/暂停 图标按钮（经典三角方块，仅图标） */
.ic-btn {
  width: 30px; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
}
.ic-btn .ic {
  width: 13px; height: 13px; fill: currentColor; display: block;
}
.net-dd { position: relative; }
.net-btn { max-width: 240px; white-space: nowrap; text-align: left; cursor: pointer; }
.dd {
  position: absolute; top: 32px; left: 0; z-index: 50;
  min-width: 230px; max-height: 340px; overflow: auto;
  background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: var(--radius-panel); box-shadow: var(--shadow-2);
  padding: 4px;
}
.dd-group { font-size: 10px; color: var(--text-3); padding: 6px 8px 2px; letter-spacing: 0.05em; }
.dd-item {
  padding: 6px 8px; font-size: 12px; color: var(--text-1); cursor: pointer;
  border-radius: var(--radius-ctrl);
}
.dd-item:hover { background: var(--bg-hover); }
.dd-item.cur { background: var(--accent-soft); color: var(--accent); }
.dd-preview {
  position: absolute; top: 32px; left: calc(100% + 10px); z-index: 50;
  width: 360px; background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: var(--radius-panel); box-shadow: var(--shadow-2); padding: 6px;
}
.dd-preview img { width: 100%; border-radius: 4px; display: block; }
.dd-preview-name { font-size: 11px; color: var(--text-2); padding: 4px 2px 0; }
.sim-chip {
  display: inline-flex; align-items: center; gap: 6px;
  height: 26px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 999px;
  font-size: 11px; color: var(--text-2); background: var(--bg-elev);
}
.sim-chip .dot { width: 7px; height: 7px; border-radius: 50%; }
.sim-chip.run .dot { background: var(--signal-green); box-shadow: 0 0 6px var(--signal-green); }
.sim-chip.pause .dot { background: var(--accent); }
.sim-chip.idle .dot { background: var(--text-3); }
.step { color: var(--text-3); font-size: 10px; }
</style>
