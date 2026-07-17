<template>
  <header class="app-header">
    <!-- 左侧：Logo + 平台名称 -->
    <div class="header-left">
      <img :src="logoSrc" alt="logo" class="header-logo" />
      <span class="header-title">RSOD Agent Platform</span>
    </div>

    <!-- 中央：核心模式切换 -->
    <div class="header-center">
      <ModeSwitcher />
    </div>
  </header>
</template>

<script setup>
import ModeSwitcher from './ModeSwitcher.vue'

const logoSrc = '/favicon.svg'
</script>

<style lang="scss" scoped>
.app-header {
  height: $header-height;
  background: rgba(10, 12, 17, 0.86);
  border-bottom: 1px solid $border-color;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  position: relative;
  padding: 0 $spacing-lg;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(18px);
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
}

.header-logo {
  width: 28px;
  height: 28px;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: $text-primary;
}

.header-center {
  display: flex;
  align-items: center;
  justify-content: center;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}
</style>
