<template>
  <section class="chat-welcome" aria-label="智能对话欢迎区">
    <h1>今天想分析什么？</h1>
    <p>提问，或添加 PCB 图片与检测文件。</p>

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
defineEmits(['use-prompt'])

const prompts = [
  '检测这张 PCB 图片',
  '帮我分析缺陷类型',
  '查看最近检测记录',
]
</script>

<style lang="scss" scoped>
.chat-welcome {
  width: min(720px, 100%);
  margin: auto;
  min-height: 0;
  padding: $spacing-xl $spacing-md;
  text-align: center;
  color: $text-regular;
}

h1 {
  margin: 0;
  color: $text-primary;
  font-size: 28px;
  font-weight: 650;
  line-height: 1.25;
}

p {
  margin: 10px auto 0;
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
    background: #fff;
    color: $text-secondary;
    box-shadow: none;
    cursor: pointer;
    padding: 0 14px;
    transition:
      background 0.18s ease,
      border-color 0.18s ease,
      color 0.18s ease;

    &:hover,
    &:focus-visible {
      border-color: $border-color-strong;
      background: #eef7ff;
      color: $primary-color-dark;
      outline: none;
    }
  }
}
</style>
