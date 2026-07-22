<template>
  <header class="app-header">
    <router-link class="header-brand" to="/chat" aria-label="芯明鉴首页">
      <span class="brand-logo"><img src="/favicon.png" alt="" /></span>
      <span class="brand-name">芯明鉴</span>
    </router-link>
    <div class="header-center">
      <ModeSwitcher />
    </div>
  </header>
</template>

<script setup>
import ModeSwitcher from './ModeSwitcher.vue'
</script>

<style lang="scss" scoped>
.app-header {
  height: $header-height;
  min-height: $header-height;
  flex: 0 0 $header-height;
  box-sizing: border-box;
  background: #fff;
  border-bottom: 1px solid #e6eef6;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  position: relative;
  padding: 0 $spacing-lg;
  box-shadow: none;
  z-index: 100;
}

.header-center {
  display: flex;
  align-items: center;
  justify-content: center;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.header-brand {
  position: absolute;
  left: $spacing-lg;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: $text-primary;
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;

  .brand-logo {
    display: inline-grid;
    place-items: center;
    width: 28px;
    height: 28px;
    overflow: hidden;
    border-radius: 8px;
    background: transparent;

    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
  }
}

@media (max-width: 560px) {
  .brand-name {
    display: none;
  }
}
</style>
