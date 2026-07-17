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
  border: 1px solid $border-color;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.055);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  user-select: none;
}

.mode-button {
  min-width: 84px;
  height: 34px;
  border: 0;
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
    box-shadow 0.18s ease;

  &:hover,
  &:focus-visible {
    color: $text-primary;
    outline: none;
  }

  &:focus-visible {
    box-shadow: 0 0 0 2px rgba(167, 139, 250, 0.42);
  }

  &.is-active {
    background: rgba(139, 92, 246, 0.2);
    color: $text-primary;
    box-shadow:
      inset 0 0 0 1px rgba(167, 139, 250, 0.18),
      0 8px 22px rgba(0, 0, 0, 0.18);
  }
}
</style>
