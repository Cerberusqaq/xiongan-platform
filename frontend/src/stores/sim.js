import { defineStore } from 'pinia'
import { apiGet, apiPost } from '../api/http'

/** 仿真状态与控制 */
export const useSimStore = defineStore('sim', {
  state: () => ({
    status: 'idle',          // idle | running | paused
    sessionId: null,
    step: 0,
    simTime: 0,
    scheme: null,
    speed: 1,
    starting: false,         // 启动请求进行中
    nets: [],                // GET /networks 列表 [{name, net_path, routes[], adds[]}]
    lastNetPath: null,
    currentEdges: [],        // 当前加载路网的边 id 列表（画布解析后写入，供 Agent/事件用）
    startScheme: 'scheme_2', // 启动方案：none | scheme_1 | scheme_2 | scheme_3
    lastError: null,
  }),
  actions: {
    async refreshStatus() {
      try {
        const s = await apiGet('/simulate/status')
        this.status = s.state
        this.sessionId = s.session_id
        this.step = s.step
        this.simTime = s.sim_time
        this.scheme = s.scheme
      } catch (e) {
        this.status = 'idle'
        this.lastError = e.message
      }
    },
    async listNetworks() {
      try { this.nets = await apiGet('/networks') } catch { /* 后端未起 */ }
    },
    async start({ netPath, routes = [], addFiles = [], scheme = 'scheme_2', schemeParams = {} }) {
      this.starting = true
      try {
        const d = await apiPost('/simulate/start', {
          net_path: netPath, route_files: routes, add_files: addFiles,
          scheme, scheme_params: schemeParams,
        })
        this.sessionId = d.session_id
        this.lastNetPath = netPath
        this.startScheme = scheme
        this.status = 'running'
        return d
      } finally {
        this.starting = false
      }
    },
    async stop() {
      await apiPost('/simulate/stop', {})
      this.status = 'idle'
      this.sessionId = null
    },
    async pause() { await apiPost('/simulate/pause', {}) },
    async resume() { await apiPost('/simulate/resume', {}) },
    async setSpeed(v) { await apiPost('/simulate/speed', { speed: v }) },
    /** 方案配置动作：POST /schemes/{id}/config {action, params} */
    async schemeAction(schemeId, action, params = {}) {
      return apiPost(`/schemes/${schemeId}/config`, { action, params })
    },
    applyStep(data) {
      if (!data) return
      if (typeof data.step === 'number') this.step = data.step
      if (typeof data.simulation_time === 'number') this.simTime = data.simulation_time
    },
  },
})
