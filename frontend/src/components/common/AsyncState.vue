<template>
  <section v-if="state !== 'success'" class="async-state" :class="[`is-${state}`, { 'is-compact': compact }]" role="status">
    <el-icon v-if="state === 'loading'" class="state-icon is-loading"><Loading /></el-icon>
    <el-icon v-else-if="state === 'error'" class="state-icon"><WarningFilled /></el-icon>
    <el-icon v-else class="state-icon"><Box /></el-icon>
    <strong>{{ title }}</strong>
    <p>{{ resolvedMessage }}</p>
    <el-button v-if="state === 'error'" type="primary" @click="$emit('retry')">{{ retryLabel }}</el-button>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Box, Loading, WarningFilled } from '@element-plus/icons-vue'

const props = defineProps({
  state: { type: String, default: 'empty' },
  message: { type: String, default: '' },
  emptyText: { type: String, default: '暂无数据' },
  retryLabel: { type: String, default: '重新加载' },
  compact: Boolean,
})

defineEmits(['retry'])

const title = computed(() => ({
  loading: '正在加载',
  error: '加载失败',
  empty: '暂无数据',
}[props.state] || '暂无数据'))

const resolvedMessage = computed(() => {
  if (props.message) return props.message
  if (props.state === 'loading') return '请稍候…'
  if (props.state === 'error') return '暂时无法获取数据，请稍后重试'
  return props.emptyText
})
</script>

<style lang="scss" scoped>
.async-state {
  display: flex;
  min-height: 220px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: $text-secondary;
  text-align: center;
  box-sizing: border-box;

  &.is-compact { min-height: 150px; padding: 18px; }

  .state-icon {
    margin-bottom: 10px;
    color: $primary-color;
    font-size: 30px;
  }

  &.is-error .state-icon { color: $danger-color; }

  strong { color: $text-primary; font-size: 15px; }
  p { margin: 6px 0 14px; font-size: 13px; line-height: 1.6; }
}
</style>
