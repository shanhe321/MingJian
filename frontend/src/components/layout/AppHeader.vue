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
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.92), rgba(248, 251, 255, 0.78)),
    radial-gradient(circle at 50% 0, rgba(91, 124, 250, 0.08), transparent 36%);
  border-bottom: 1px solid $border-color;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  position: relative;
  padding: 0 $spacing-lg;
  box-shadow: 0 10px 30px rgba(40, 58, 96, 0.06);
  backdrop-filter: blur(20px) saturate(1.12);
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
  border-radius: 8px;
  filter: drop-shadow(0 8px 14px rgba(91, 124, 250, 0.18));
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: $text-primary;
  letter-spacing: 0;
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
