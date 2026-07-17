<template>
  <section class="chat-welcome" aria-label="智能对话欢迎区">
    <div class="welcome-mark">
      <el-icon><Aim /></el-icon>
    </div>
    <h1>开始一次 PCB 缺陷分析</h1>
    <p>上传图片、批量文件或视频，也可以直接询问检测指标、历史记录和模型知识。</p>

    <div class="welcome-prompts" aria-label="示例提示">
      <button
        v-for="prompt in prompts"
        :key="prompt"
        type="button"
        @click="$emit('use-prompt', prompt)"
      >
        {{ prompt }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { Aim } from '@element-plus/icons-vue'

defineEmits(['use-prompt'])

const prompts = [
  '检测这张 PCB 图片',
  '今天检测了多少次？',
  '什么是 IoU？',
]
</script>

<style lang="scss" scoped>
.chat-welcome {
  width: min(720px, 100%);
  margin: auto;
  padding: $spacing-xl $spacing-md;
  text-align: center;
  color: $text-regular;
}

.welcome-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  margin-bottom: $spacing-md;
  border: 1px solid rgba(167, 139, 250, 0.24);
  border-radius: 16px;
  background: rgba(139, 92, 246, 0.12);
  color: $primary-color-light;

  .el-icon {
    font-size: 24px;
  }
}

h1 {
  margin: 0;
  color: $text-primary;
  font-size: 28px;
  font-weight: 650;
  line-height: 1.25;
}

p {
  max-width: 560px;
  margin: $spacing-md auto 0;
  color: $text-secondary;
  font-size: 15px;
  line-height: 1.7;
}

.welcome-prompts {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: $spacing-sm;
  margin-top: $spacing-lg;

  button {
    height: 34px;
    border: 1px solid $border-color;
    border-radius: 999px;
    background: rgba(28, 34, 43, 0.74);
    color: $text-secondary;
    cursor: pointer;
    padding: 0 14px;
    transition:
      background 0.18s ease,
      border-color 0.18s ease,
      color 0.18s ease;

    &:hover,
    &:focus-visible {
      border-color: $border-color-strong;
      background: $surface-color-elevated;
      color: $text-primary;
      outline: none;
    }
  }
}
</style>
