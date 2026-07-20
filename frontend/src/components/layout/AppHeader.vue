<template>
  <header class="app-header">
    <router-link class="header-brand" to="/chat" aria-label="PCB 智能检测平台首页">
      <span class="brand-logo"><img :src="rsodLogo" alt="" /></span>
    </router-link>
    <div class="header-center">
      <ModeSwitcher />
    </div>
  </header>
</template>

<script setup>
import rsodLogo from '@/assets/images/rsod-logo.png'
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
  justify-content: center;
  text-decoration: none;

  .brand-logo {
    display: inline-grid;
    place-items: center;
    width: 34px;
    height: 34px;
    overflow: hidden;
    border: 1px solid $border-color;
    border-radius: 10px;
    background: #fff;

    img {
      width: 32px;
      height: 32px;
      max-width: none;
      object-fit: cover;
      transform: translateX(-3%) scale(1.55);
    }
  }
}
</style>
