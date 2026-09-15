<script setup>
/**
 * 屏幕中央加载窗：用于"启动仿真/等待首批数据"这类需要若干秒的加载过程。
 * pointer-events: none —— 不挡住底层操作（后端异常时用户仍可手动点启动/切换方案）。
 */
defineProps({
  title: { type: String, default: '正在加载…' },
  hint: { type: String, default: '' },
})
</script>

<template>
  <div class="loading-overlay">
    <div class="loading-card">
      <div class="spinner" aria-hidden="true"></div>
      <div class="title">{{ title }}</div>
      <div v-if="hint" class="hint">{{ hint }}</div>
    </div>
  </div>
</template>

<style scoped>
.loading-overlay {
  position: fixed; inset: 0; z-index: 60;
  display: flex; align-items: center; justify-content: center;
  /* 兜底纯色 → 支持 color-mix 的浏览器用主题色半透明 */
  background: rgb(10 10 12 / 0.42);
  background: color-mix(in oklab, var(--bg-base) 62%, transparent);
  backdrop-filter: blur(2px);
  pointer-events: none;
}
.loading-card {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  min-width: 220px; max-width: 320px; padding: 20px 26px;
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: var(--radius-panel); box-shadow: var(--shadow-2);
}
.spinner {
  width: 30px; height: 30px; border-radius: 50%;
  border: 3px solid var(--border-strong);
  border-top-color: var(--accent);
  animation: dsh-spin 0.9s linear infinite;
}
@keyframes dsh-spin { to { transform: rotate(360deg); } }
.title { font-size: 14px; font-weight: 600; color: var(--text-1); }
.hint { font-size: 12px; line-height: 1.55; color: var(--text-2); text-align: center; }
</style>
