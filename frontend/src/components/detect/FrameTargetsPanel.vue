<template>
  <section class="targets-panel">
    <header>
      <div>
        <span class="eyebrow">LIVE TARGETS</span>
        <h2>当前帧目标</h2>
      </div>
      <span class="target-count">{{ detections.length }}</span>
    </header>

    <div v-if="detections.length" class="target-list">
      <article v-for="(target, index) in detections" :key="`${target.class_id}-${index}`" class="target-item">
        <span class="target-index">{{ String(index + 1).padStart(2, '0') }}</span>
        <span class="target-copy">
          <strong>{{ target.class_name_cn || target.class_name || '未知目标' }}</strong>
          <small>{{ target.class_name || `Class ${target.class_id ?? '-'}` }}</small>
        </span>
        <span class="confidence">{{ formatConfidence(target.confidence ?? target.conf) }}</span>
      </article>
    </div>

    <div v-else class="empty-targets">
      <span><el-icon><Aim /></el-icon></span>
      <strong>等待检测目标</strong>
      <small>启动后，当前帧识别结果会实时显示在这里。</small>
    </div>
  </section>
</template>

<script setup>
import { Aim } from '@element-plus/icons-vue'

defineProps({ detections: { type: Array, default: () => [] } })

function formatConfidence(value) {
  const numeric = Number(value || 0)
  return `${(numeric <= 1 ? numeric * 100 : numeric).toFixed(1)}%`
}
</script>

<style lang="scss" scoped>
.targets-panel {
  min-height: 0;
  flex: 1;
  padding: 11px 13px 10px;
  background: transparent;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

header,
.target-item {
  display: flex;
  align-items: center;
}

header {
  justify-content: space-between;
  flex: 0 0 auto;
  margin-bottom: 7px;
}

.eyebrow {
  color: $primary-color;
  font-size: 8px;
  font-weight: 750;
  letter-spacing: 0.14em;
}

h2 {
  margin: 3px 0 0;
  color: $text-primary;
  font-size: 14px;
}

.target-count {
  display: inline-grid;
  place-items: center;
  min-width: 26px;
  height: 26px;
  padding: 0 7px;
  border-radius: 9px;
  background: rgba(91, 124, 250, 0.09);
  color: $primary-color;
  font-size: 11px;
  font-weight: 700;
}

.target-list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.target-item {
  gap: 9px;
  min-height: 48px;
  padding: 7px 3px;
  border-top: 1px solid rgba(226, 232, 240, 0.7);
}

.target-index {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  background: #f2f5fa;
  color: $text-secondary;
  font-size: 9px;
  font-weight: 700;
}

.target-copy {
  min-width: 0;
  flex: 1;

  strong,
  small { display: block; }
  strong { color: $text-primary; font-size: 11px; }
  small { margin-top: 2px; color: $text-placeholder; font-size: 8px; }
}

.confidence {
  color: $success-color;
  font-size: 10px;
  font-weight: 700;
}

.empty-targets {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: $text-secondary;
  text-align: center;

  > span {
    display: inline-grid;
    place-items: center;
    width: 38px;
    height: 38px;
    margin-bottom: 6px;
    border-radius: 12px;
    background: rgba(91, 124, 250, 0.08);
    color: $primary-color;
  }

  strong { color: $text-primary; font-size: 11px; }
  small { max-width: 220px; margin-top: 4px; font-size: 9px; line-height: 1.5; }
}
</style>
