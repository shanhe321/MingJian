<template>
  <nav class="mode-switcher" aria-label="核心模式切换">
    <button
      v-for="mode in modes"
      :key="mode.path"
      type="button"
      class="mode-button"
      :class="{ 'is-active': isActive(mode.path) }"
      :aria-pressed="isActive(mode.path)"
      @click="go(mode.path)"
    >
      {{ mode.label }}
    </button>
  </nav>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const modes = [
  { label: 'Chat', path: '/chat' },
  { label: 'Detect', path: '/detection' },
]

function isActive(path) {
  return route.path === path || route.path.startsWith(`${path}/`)
}

function go(path) {
  if (!isActive(path)) {
    router.push(path)
  }
}
</script>

<style lang="scss" scoped>
.mode-switcher {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid rgba(207, 216, 230, 0.92);
  border-radius: 999px;
  background: #fff;
  box-shadow: none;
  user-select: none;
}

.mode-button {
  min-width: 84px;
  height: 34px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: $text-secondary;
  cursor: pointer;
  font-weight: 600;
  line-height: 1;
  user-select: none;
  transition:
    background 0.18s ease,
    color 0.18s ease,
    border-color 0.18s ease;

  &:hover,
  &:focus-visible {
    color: $text-primary;
    outline: none;
  }

  &:focus-visible {
    border-color: $border-color-strong;
  }

  &.is-active {
    background: #eaf4ff;
    border-color: #bfd8f4;
    color: $primary-color-dark;
    box-shadow: none;
  }
}
</style>
