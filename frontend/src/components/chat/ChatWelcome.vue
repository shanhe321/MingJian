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
  position: relative;

  &::before {
    content: "";
    position: absolute;
    inset: 12% 16% auto;
    height: 220px;
    background:
      radial-gradient(circle at 55% 40%, rgba(91, 124, 250, 0.12), transparent 60%),
      radial-gradient(circle at 35% 35%, rgba(139, 92, 246, 0.1), transparent 58%);
    filter: blur(8px);
    pointer-events: none;
    z-index: -1;
  }
}

.welcome-mark {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin-bottom: $spacing-md;
  border: 1px solid rgba(91, 124, 250, 0.22);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(245, 248, 255, 0.64)),
    linear-gradient(135deg, rgba(91, 124, 250, 0.14), rgba(139, 92, 246, 0.12));
  color: $primary-color-light;
  box-shadow:
    0 18px 42px rgba(91, 124, 250, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.95);

  &::before {
    content: "";
    position: absolute;
    inset: -18px;
    border-radius: 26px;
    background: radial-gradient(circle, rgba(91, 124, 250, 0.16), transparent 68%);
    z-index: -1;
  }

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
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(246, 249, 255, 0.78));
    color: $text-secondary;
    box-shadow:
      0 8px 22px rgba(40, 58, 96, 0.05),
      inset 0 1px 0 rgba(255, 255, 255, 0.92);
    cursor: pointer;
    padding: 0 14px;
    transition:
      background 0.18s ease,
      border-color 0.18s ease,
      color 0.18s ease;

    &:hover,
    &:focus-visible {
      border-color: $border-color-strong;
      background:
        linear-gradient(135deg, rgba(91, 124, 250, 0.1), rgba(139, 92, 246, 0.08)),
        #fff;
      color: $text-primary;
      transform: translateY(-1px);
      outline: none;
    }
  }
}
</style>
