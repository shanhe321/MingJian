<template>
  <section class="stats-grid" aria-label="实时检测统计">
    <article v-for="item in items" :key="item.label" class="stat-card">
      <span class="stat-icon"><el-icon><component :is="item.icon" /></el-icon></span>
      <span class="stat-copy"><strong>{{ item.value }}</strong><small>{{ item.label }}</small></span>
    </article>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Aim, DataLine, Odometer, Timer } from '@element-plus/icons-vue'

const props = defineProps({
  fps: { type: Number, default: 0 },
  objectCount: { type: Number, default: 0 },
  frameCount: { type: Number, default: 0 },
  inferenceTime: { type: Number, default: 0 },
})

const items = computed(() => [
  { label: '当前 FPS', value: Number(props.fps || 0).toFixed(1), icon: Odometer },
  { label: '当前目标', value: props.objectCount || 0, icon: Aim },
  { label: '已处理帧', value: props.frameCount || 0, icon: DataLine },
  { label: '推理耗时', value: `${Number(props.inferenceTime || 0).toFixed(0)} ms`, icon: Timer },
])
</script>

<style lang="scss" scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  flex: 0 0 auto;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(207, 216, 230, 0.7);
  box-sizing: border-box;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 62px;
  padding: 8px 9px;
  border: 1px solid rgba(207, 216, 230, 0.62);
  border-radius: 12px;
  background: rgba(248, 250, 255, 0.78);
  box-sizing: border-box;
}

.stat-icon {
  display: inline-grid;
  place-items: center;
  width: 29px;
  height: 29px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(91, 124, 250, 0.12), rgba(139, 92, 246, 0.08));
  color: $primary-color;
  flex: 0 0 auto;
}

.stat-copy {
  min-width: 0;

  strong,
  small { display: block; }

  strong {
    overflow: hidden;
    color: $text-primary;
    font-size: 15px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    margin-top: 2px;
    color: $text-secondary;
    font-size: 9px;
  }
}
</style>
