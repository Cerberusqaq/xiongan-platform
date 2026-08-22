<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import PanelCard from './ui/PanelCard.vue'
import AppButton from './ui/AppButton.vue'
import { useAgentStore } from '../stores/agent'
import { useUiStore } from '../stores/ui'
import { useSimStore } from '../stores/sim'

const agent = useAgentStore()
const ui = useUiStore()
const sim = useSimStore()
const input = ref('')

// 工具详情弹窗
const toolsOpen = ref(false)
onMounted(() => { agent.fetchTools() })

// LLM 模型切换（可选免费模型，运行时生效）
const selModel = ref('')
watch(() => agent.status?.model, (m) => { if (m) selModel.value = m }, { immediate: true })
async function onModelChange() {
  const prev = agent.status?.model
  try {
    const d = await agent.switchModel(selModel.value)
    if (!d.ok) selModel.value = prev
  } catch {
    selModel.value = prev
  }
}
async function onResetMemory() {
  await agent.resetMemory()
}

function argSummary(args) {
  if (!args || !Object.keys(args).length) return ''
  const s = JSON.stringify(args, null, 0)
  return s.length > 36 ? s.slice(0, 36) + '…' : s
}

// 预设问题模板：道路留空 → 下拉选择后发送
const TEMPLATES = [
  {
    label: '应急调控',
    fields: [{ key: 'f1', label: '道路', type: 'edge' }],
    build: (v) => `检测到 ${v.f1} 附近突发车流，请分析现状并执行应急调控`,
  },
  {
    label: '路径规划',
    fields: [
      { key: 'from', label: '起点', type: 'edge' },
      { key: 'to', label: '终点', type: 'edge' },
    ],
    build: (v) => `我想从 ${v.from} 去 ${v.to}，请规划最优路径并给出驾驶建议`,
  },
  {
    label: '全局巡检',
    fields: [],
    build: () => '请巡检全局路网，如发现拥堵区域请给出协调建议并执行',
  },
]
const tmplSel = ref({}) // `${label}.${key}` -> 边 id

function sendTemplate(t) {
  const v = {}
  for (const f of t.fields) {
    const val = tmplSel.value[`${t.label}.${f.key}`]
    if (!val) return
    v[f.key] = val
  }
  send(t.build(v))
}

const listRef = ref(null)
async function send(text = input.value) {
  if (!text.trim() || agent.thinking) return
  input.value = ''
  try {
    await agent.chat(text)
  } catch { /* 错误已存入 agent.error */ }
  await nextTick()
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}
</script>

<template>
  <PanelCard title="Traffic Copilot · 智能体" class="agent-panel">
    <template #extra>
      <button class="tools-btn" @click="toolsOpen = true" title="查看 Agent 可用的全部技能（工具）">
        工具详情
      </button>
    </template>
    <div ref="listRef" class="msgs">
      <div v-if="!agent.messages.length" class="empty">
        <p>向 AI 协管员下达指令，或从下方模板选择道路后发送。</p>
        <p class="empty-sub">工具调用将真实作用于正在运行的仿真。</p>
      </div>

      <div v-for="(m, i) in agent.messages" :key="i" class="msg" :class="m.role">
        <div class="bubble">{{ m.content }}</div>
        <div v-if="m.toolCalls.length" class="tools">
          <details v-for="(tc, j) in m.toolCalls" :key="j" class="tool">
            <summary>
              <span class="tool-dot" />
              <span class="tool-name mono">{{ tc.tool }}</span>
              <span class="tool-args mono">{{ argSummary(tc.args) }}</span>
              <span class="tool-ok" :class="tc.result && tc.result.ok ? 'ok' : 'fail'">
                {{ tc.result && tc.result.ok ? '成功' : '失败' }}
              </span>
            </summary>
            <pre v-if="ui.viewMode === 'pro'" class="tool-detail mono">{{ JSON.stringify(tc, null, 2) }}</pre>
          </details>
        </div>
      </div>

      <div v-if="agent.thinking" class="msg assistant">
        <div class="bubble typing">
          <span class="dot" /><span class="dot" /><span class="dot" />
          <span class="typing-text">Agent 正在分析态势并调用工具…</span>
        </div>
      </div>

      <div v-if="agent.error" class="err mono">{{ agent.error }}</div>
    </div>

    <div class="actions">
      <div class="model-row">
        <span class="model-label">LLM 模型</span>
        <select v-model="selModel" class="model-sel mono" @change="onModelChange"
          :disabled="!(agent.status?.available_models || []).length" title="切换 LLM 模型（免费）">
          <option v-for="m in agent.status?.available_models || []" :key="m" :value="m">{{ m }}</option>
        </select>
        <button class="reset-mem" @click="onResetMemory" title="清空 Agent 会话记忆与对比基线">清空记忆</button>
      </div>
      <div class="templates">
      <div v-for="t in TEMPLATES" :key="t.label" class="tmpl">
        <span class="tmpl-label">{{ t.label }}</span>
        <select
          v-for="f in t.fields" :key="f.key"
          v-model="tmplSel[`${t.label}.${f.key}`]"
          class="tmpl-sel mono" :title="f.label"
        >
          <option value="" disabled>选{{ f.label }}</option>
          <option v-for="eid in sim.currentEdges" :key="eid" :value="eid">{{ eid }}</option>
        </select>
        <button class="tmpl-send" @click="sendTemplate(t)">发送</button>
      </div>
    </div>

      <div class="input-row">
        <input
          v-model="input" class="input mono"
          placeholder="自定义指令，回车发送…"
          @keyup.enter="send()"
        />
        <AppButton variant="primary" :disabled="agent.thinking" @click="send()">发送</AppButton>
      </div>
    </div>
  </PanelCard>

  <!-- 工具详情弹窗 -->
  <Teleport to="body">
    <div v-if="toolsOpen" class="tools-mask" @click.self="toolsOpen = false">
      <div class="tools-panel">
        <div class="tools-head">
          <span class="tools-title">Agent 技能清单（{{ agent.tools.length }}）</span>
          <button class="tools-close" @click="toolsOpen = false">×</button>
        </div>
        <div v-if="!agent.tools.length" class="tools-empty">技能列表加载中…</div>
        <div v-for="t in agent.tools" :key="t.name" class="tool-card">
          <div class="tool-name-row">
            <span class="tool-name mono">{{ t.name }}</span>
            <span class="tool-kind">function</span>
          </div>
          <div class="tool-desc">{{ t.description }}</div>
          <div v-if="t.args.length" class="tool-args">
            <div v-for="a in t.args" :key="a.name" class="arg-row">
              <span class="arg-name mono">{{ a.name }}</span>
              <span class="arg-req" :class="a.required ? 'req' : 'opt'">{{ a.required ? '必填' : '可选' }}</span>
              <span class="arg-desc">{{ a.desc }}</span>
              <span v-if="a.enum" class="arg-extra mono">枚举: {{ a.enum.join(' / ') }}</span>
              <span v-if="a.range" class="arg-extra mono">范围: {{ a.range }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.agent-panel { height: 100%; }
/* PanelCard 的 panel-body 默认是整体滚动容器；改为 flex 纵向布局，
   让对话区（中间大块）独立滚动、操作栏固定沉底 */
.agent-panel :deep(.panel-body) {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.msgs {
  flex: 1; min-height: 0;
  overflow: auto;
  display: flex; flex-direction: column; gap: var(--space-3);
  /* 对话显示栏：独立视觉容器，突出中间大块 */
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  padding: var(--space-3);
}
.empty { margin: auto; text-align: center; color: var(--text-3); font-size: 12px; }
.empty-sub { font-size: 11px; opacity: 0.8; }
.msg.user { align-self: flex-end; }
.msg.assistant { align-self: flex-start; }
.bubble {
  max-width: 92%; padding: 8px 12px; border-radius: 10px;
  font-size: 13px; line-height: 1.6; white-space: pre-wrap;
}
.user .bubble {
  background: var(--accent-soft); color: var(--accent);
  border-bottom-right-radius: 3px;
}
.assistant .bubble {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-bottom-left-radius: 3px;
}
.tools { margin-top: 4px; display: flex; flex-direction: column; gap: 4px; }
.tool {
  border: 1px solid var(--border); border-radius: var(--radius-ctrl);
  background: var(--bg-panel); font-size: 12px;
}
.tool summary { display: flex; gap: 8px; padding: 5px 8px; cursor: pointer; list-style: none; align-items: center; }
.tool summary::-webkit-details-marker { display: none; }
.tool-dot { width: 6px; height: 6px; border-radius: 2px; background: var(--accent); flex: 0 0 auto; }
.tool-name { color: var(--accent); white-space: nowrap; }
.tool-args { color: var(--text-3); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-ok { margin-left: auto; font-size: 11px; white-space: nowrap; }
.tool-ok.ok { color: var(--signal-green); }
.tool-ok.fail { color: var(--signal-red); }
.tool-detail { margin: 0; padding: 6px 8px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-2); overflow: auto; }
.typing { display: flex; align-items: center; gap: 4px; }
.typing .dot { width: 5px; height: 5px; border-radius: 50%; background: var(--text-3); animation: blink 1.2s infinite; }
.typing .dot:nth-child(2) { animation-delay: 0.2s; }
.typing .dot:nth-child(3) { animation-delay: 0.4s; }
.typing-text { margin-left: 6px; color: var(--text-3); font-size: 12px; }
@keyframes blink { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }
.err { font-size: 11px; color: var(--signal-red); padding: 4px 8px; background: var(--signal-red-soft); border-radius: 4px; }
/* 底部操作栏：模板 + 自定义输入，固定在对话区下方不随滚动 */
.actions {
  flex: 0 0 auto;
  display: flex; flex-direction: column; gap: var(--space-2);
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border);
}
.templates { display: flex; flex-direction: column; gap: 6px; }
.model-row { display: flex; align-items: center; gap: 6px; }
.model-label { font-size: 11px; color: var(--text-2); flex: 0 0 auto; }
.model-sel {
  flex: 1; min-width: 0; height: 24px; padding: 0 4px;
  background: var(--bg-elev); color: var(--text-1);
  border: 1px solid var(--border); border-radius: var(--radius-ctrl); font-size: 11px;
}
.reset-mem {
  flex: 0 0 auto; height: 24px; padding: 0 8px; white-space: nowrap;
  border: 1px solid var(--border-strong); border-radius: var(--radius-ctrl);
  background: var(--bg-elev); color: var(--text-2); font-size: 11px; cursor: pointer;
}
.reset-mem:hover { border-color: var(--signal-red); color: var(--signal-red); }
.tmpl { display: flex; align-items: center; gap: 5px; }
.tmpl-label { flex: 0 0 52px; font-size: 11px; color: var(--text-2); }
.tmpl-sel {
  flex: 1; min-width: 0; height: 24px; padding: 0 4px;
  background: var(--bg-elev); color: var(--text-1);
  border: 1px solid var(--border); border-radius: var(--radius-ctrl); font-size: 11px;
}
.tmpl-send {
  flex: 0 0 40px; height: 24px; border: 1px solid var(--accent); border-radius: var(--radius-ctrl);
  background: var(--accent-soft); color: var(--accent); font-size: 11px; cursor: pointer; white-space: nowrap;
}
.tmpl-send:hover { background: var(--accent); color: oklch(0.16 0.01 80); }
.input-row { display: flex; gap: var(--space-2); }
.input {
  flex: 1; min-width: 0; height: 30px; padding: 0 10px;
  background: var(--bg-elev); color: var(--text-1);
  border: 1px solid var(--border); border-radius: var(--radius-ctrl);
  font-size: 12px; outline: none;
}
.input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); }

/* 工具详情按钮（标题栏右侧） */
.tools-btn {
  height: 20px; padding: 0 8px; white-space: nowrap;
  border: 1px solid var(--border-strong); border-radius: var(--radius-ctrl);
  background: var(--bg-elev); color: var(--text-2); font-size: 11px; cursor: pointer;
}
.tools-btn:hover { border-color: var(--accent); color: var(--accent); }

/* 工具详情弹窗 */
.tools-mask {
  position: fixed; inset: 0; z-index: 150;
  background: rgb(0 0 0 / 0.45);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.tools-panel {
  width: min(560px, 92vw); max-height: 82vh; overflow: auto;
  background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: var(--radius-panel); box-shadow: var(--shadow-2);
  padding: var(--space-4);
}
.tools-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3); }
.tools-title { font-size: 15px; font-weight: 700; }
.tools-close { border: none; background: none; color: var(--text-3); font-size: 20px; cursor: pointer; }
.tools-close:hover { color: var(--signal-red); }
.tools-empty { font-size: 12px; color: var(--text-3); padding: 16px 0; text-align: center; }
.tool-card {
  border: 1px solid var(--border); border-radius: var(--radius-panel);
  background: var(--bg-elev); padding: var(--space-3); margin-bottom: var(--space-3);
}
.tool-name-row { display: flex; align-items: center; gap: 8px; }
.tool-name { font-size: 13px; color: var(--accent); font-weight: 600; }
.tool-kind {
  font-size: 10px; color: var(--text-3);
  border: 1px solid var(--border); border-radius: 999px; padding: 1px 6px;
}
.tool-desc { font-size: 12px; color: var(--text-2); margin: 6px 0 var(--space-2); line-height: 1.6; }
.tool-args { display: flex; flex-direction: column; gap: 3px; }
.arg-row { display: flex; align-items: baseline; gap: 8px; font-size: 11px; flex-wrap: wrap; }
.arg-name { color: var(--text-1); }
.arg-req { flex: 0 0 auto; font-size: 10px; border-radius: 3px; padding: 0 4px; }
.arg-req.req { color: var(--signal-red); background: var(--signal-red-soft); }
.arg-req.opt { color: var(--text-3); background: var(--bg-active); }
.arg-desc { color: var(--text-2); }
.arg-extra { color: var(--text-3); font-size: 10px; }
</style>
