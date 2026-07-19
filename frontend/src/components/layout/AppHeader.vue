<template>
  <header class="app-header">
    <div class="header-center">
      <ModeSwitcher />
    </div>
    <span class="header-context">PCB AI WORKSPACE</span>
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
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.92), rgba(248, 251, 255, 0.78)),
    radial-gradient(circle at 50% 0, rgba(91, 124, 250, 0.08), transparent 36%);
  border-bottom: 1px solid $border-color;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  position: relative;
  padding: 0 $spacing-lg;
  box-shadow: 0 10px 30px rgba(40, 58, 96, 0.06);
  backdrop-filter: blur(20px) saturate(1.12);
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

.header-context {
  color: $text-placeholder;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

@media (max-width: 560px) {
  .header-context {
    display: none;
  }
}
</style>
