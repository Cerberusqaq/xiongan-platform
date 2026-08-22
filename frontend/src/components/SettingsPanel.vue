<script setup>
import { useUiStore } from '../stores/ui'

defineProps({ open: Boolean })
const emit = defineEmits(['close'])
const ui = useUiStore()

const ITEMS = [
  { key: 'dblClickReset', label: '双击画布复位视图', desc: '关闭后双击不再复位缩放/平移' },
  { key: 'showMedian', label: '显示中央分隔线', desc: '双向道路之间的黄色虚线' },
  { key: 'showLights', label: '显示信号灯', desc: '路口逐进口信号灯' },
  { key: 'showVehicles', label: '显示车辆', desc: '关闭后可专注查看路网' },
  { key: 'infoAutoRefresh', label: '选中信息自动刷新', desc: '每 4 秒刷新选中对象的数据' },
  { key: 'showLegend', label: '显示事件图例', desc: '左上角事故/施工/突发车流颜色图例' },
  { key: 'showEvalCharts', label: '显示离线评估图表', desc: '底部离线评估柱状图与方案对比表格（默认关闭）' },
]
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="mask" @click.self="emit('close')">
      <div class="panel">
        <div class="head">
          <span class="title">设置</span>
          <button class="close" @click="emit('close')">×</button>
        </div>
        <div v-for="it in ITEMS" :key="it.key" class="item">
          <div class="txt">
            <div class="label">{{ it.label }}</div>
            <div class="desc">{{ it.desc }}</div>
          </div>
          <button class="sw" :class="{ on: ui.settings[it.key] }"
            @click="ui.setSetting(it.key, !ui.settings[it.key])">
            <span class="knob" />
          </button>
        </div>
        <div class="item">
          <div class="txt">
            <div class="label">左侧栏模式</div>
            <div class="desc">堆叠同时显示三个子栏 / 单栏切换（一次只显示一个）</div>
          </div>
          <div class="seg">
            <button :class="{ on: ui.settings.leftMode === 'stacked' }"
              @click="ui.setSetting('leftMode', 'stacked')">堆叠</button>
            <button :class="{ on: ui.settings.leftMode === 'tabs' }"
              @click="ui.setSetting('leftMode', 'tabs')">单栏</button>
          </div>
        </div>
        <div class="item">
          <div class="txt">
            <div class="label">重置布局</div>
            <div class="desc">面板尺寸恢复默认（左右栏、底部栏、左栏高度）</div>
          </div>
          <button class="reset" @click="ui.resetLayout()">重置</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed; inset: 0; z-index: 100;
  background: rgb(0 0 0 / 0.45);
  display: flex; align-items: center; justify-content: center;
}
.panel {
  width: 340px; padding: var(--space-4);
  background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: var(--radius-panel); box-shadow: var(--shadow-2);
}
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4); }
.title { font-size: 15px; font-weight: 700; }
.close {
  border: none; background: none; color: var(--text-3); font-size: 18px; cursor: pointer;
}
.close:hover { color: var(--signal-red); }
.item { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 8px 0; border-top: 1px solid var(--border); }
.label { font-size: 13px; color: var(--text-1); }
.desc { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.sw {
  width: 40px; height: 22px; border-radius: 999px; border: 1px solid var(--border-strong);
  background: var(--bg-elev); cursor: pointer; position: relative; flex: 0 0 auto;
  transition: background var(--dur-fast);
}
.sw.on { background: var(--accent); border-color: var(--accent); }
.reset {
  flex: 0 0 auto; height: 24px; padding: 0 12px;
  border: 1px solid var(--accent); border-radius: var(--radius-ctrl);
  background: var(--accent-soft); color: var(--accent); font-size: 11px; cursor: pointer;
}
.reset:hover { background: var(--accent); color: oklch(0.16 0.01 80); }
.seg { display: inline-flex; border: 1px solid var(--border-strong); border-radius: var(--radius-ctrl); overflow: hidden; flex: 0 0 auto; }
.seg button {
  height: 22px; padding: 0 10px; border: none; background: var(--bg-elev);
  color: var(--text-2); font-size: 11px; cursor: pointer; white-space: nowrap;
}
.seg button + button { border-left: 1px solid var(--border-strong); }
.seg button.on { background: var(--accent); color: oklch(0.16 0.01 80); }
.knob {
  position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
  background: var(--text-2); transition: left var(--dur-fast) var(--ease-out), background var(--dur-fast);
}
.sw.on .knob { left: 20px; background: oklch(0.16 0.01 80); }
</style>
