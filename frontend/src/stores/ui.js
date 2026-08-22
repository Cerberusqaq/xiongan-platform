import { defineStore } from 'pinia'

const LAYOUT_DEFAULTS = { leftW: 300, rightW: 380, bottomH: 200, metricsH: 210, schemeH: 330 }
const LAYOUT_CLAMP = {
  leftW: [180, 560], rightW: [280, 640], bottomH: [100, 420],
  metricsH: [110, 480], schemeH: [180, 640],
}

function loadLayout() {
  try {
    const raw = JSON.parse(localStorage.getItem('ui-layout') || '{}')
    const out = { ...LAYOUT_DEFAULTS, ...raw }
    // 钳制：防止旧的大 bottomH 持久化导致底部栏占屏过高
    out.bottomH = Math.max(100, Math.min(420, out.bottomH))
    return out
  } catch {
    return { ...LAYOUT_DEFAULTS }
  }
}

const SETTINGS_DEFAULTS = {
  dblClickReset: true,   // 双击画布复位视图
  showMedian: true,      // 显示中央分隔线
  showLights: true,      // 显示信号灯
  showVehicles: true,    // 显示车辆
  infoAutoRefresh: true, // 选中信息自动刷新
  showLegend: true,      // 左上角事件图例（事故/施工/突发车流）
  showEvalCharts: false, // 底部离线评估柱状图与对比表格（默认关闭）
  leftMode: 'stacked',   // 左栏模式：stacked 堆叠（默认）| tabs 单栏切换
  leftTab: 'metrics',    // 单栏模式当前子栏：metrics | scheme | event
  customMetrics: [],   // 自定义指标默认全关：默认只显示基础四卡（在网车辆/平均速度/平均等待/平均排队）
}

// 设置版本：升级时用于迁移/清除旧版遗留字段（如自定义指标默认值变更）
const SETTINGS_VER = 2

function loadSettings() {
  try {
    const raw = JSON.parse(localStorage.getItem('ui-settings') || '{}')
    // 版本迁移：v2 起自定义指标默认全关（只显示基础四卡），
    // 清除旧版遗留的 customMetrics，避免 localStorage 旧值覆盖新默认
    if (raw.__ver !== SETTINGS_VER) {
      delete raw.customMetrics
      raw.__ver = SETTINGS_VER
    }
    return { ...SETTINGS_DEFAULTS, ...raw }
  } catch {
    return { ...SETTINGS_DEFAULTS }
  }
}

/** UI 状态：主题（深/浅）+ 视图（普通/专业）+ 面板尺寸（可拖拽，持久化）+ 设置 */
export const useUiStore = defineStore('ui', {
  state: () => ({
    theme: localStorage.getItem('ui-theme') || 'dark',
    viewMode: localStorage.getItem('ui-view') || 'normal', // normal | pro
    settings: loadSettings(),
    testMode: false,           // 测试车辆选路模式（画布点击选边）
    spotlight: null,           // 跨组件聚焦请求 {type:'vehicle'|'edge'|'node', id}（NetCanvas 监听）
    ...loadLayout(),
  }),
  actions: {
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem('ui-theme', this.theme)
      this.apply()
    },
    setViewMode(mode) {
      this.viewMode = mode
      localStorage.setItem('ui-view', mode)
    },
    setSetting(key, val) {
      this.settings[key] = val
      this.settings.__ver = SETTINGS_VER
      localStorage.setItem('ui-settings', JSON.stringify(this.settings))
    },
    setTestMode(v) { this.testMode = v },
    setSpotlight(sp) { this.spotlight = sp },
    apply() {
      document.documentElement.dataset.theme = this.theme
    },

    setLeftW(v) { this.leftW = this._clamp('leftW', v); this._saveLayout() },
    setRightW(v) { this.rightW = this._clamp('rightW', v); this._saveLayout() },
    setBottomH(v) { this.bottomH = this._clamp('bottomH', v); this._saveLayout() },
    setMetricsH(v) { this.metricsH = this._clamp('metricsH', v); this._saveLayout() },
    setSchemeH(v) { this.schemeH = this._clamp('schemeH', v); this._saveLayout() },
    resetLayout() {
      for (const k of Object.keys(LAYOUT_DEFAULTS)) this[k] = LAYOUT_DEFAULTS[k]
      this._saveLayout()
    },
    _clamp(key, v) {
      const [lo, hi] = LAYOUT_CLAMP[key]
      return Math.max(lo, Math.min(hi, Math.round(v)))
    },
    _saveLayout() {
      localStorage.setItem('ui-layout', JSON.stringify({
        leftW: this.leftW, rightW: this.rightW, bottomH: this.bottomH,
        metricsH: this.metricsH, schemeH: this.schemeH,
      }))
    },
  },
})
