<template>
  <div class="main-layout">
    <!-- 顶部导航栏 -->
    <AppHeader />

    <!-- 下方区域：侧边栏 + 内容区 -->
    <div class="layout-body">
      <AppSidebar />

      <!-- 页面内容区 -->
      <main class="layout-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import { onMounted } from 'vue'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
onMounted(() => userStore.fetchUserInfo())
</script>

<style lang="scss" scoped>
.main-layout {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: $bg-color-dark;
}

.layout-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.layout-content {
  flex: 1;
  min-width: 0;
  position: relative;
  isolation: isolate;
  background:
    radial-gradient(circle at 72% 5%, rgba(91, 124, 250, 0.16), transparent 34rem),
    radial-gradient(circle at 18% 10%, rgba(139, 92, 246, 0.11), transparent 28rem),
    radial-gradient(circle at 52% 0, rgba(72, 184, 247, 0.08), transparent 22rem),
    linear-gradient(180deg, #f8fbff 0%, #f5f7fc 100%),
    $bg-color;
  overflow-y: auto;
  padding: $spacing-lg $spacing-xl;

  &::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image:
      linear-gradient(rgba(91, 124, 250, 0.035) 1px, transparent 1px),
      linear-gradient(90deg, rgba(91, 124, 250, 0.028) 1px, transparent 1px);
    background-size: 44px 44px;
    mask-image: radial-gradient(circle at 50% 8%, rgba(0, 0, 0, 0.55), transparent 62%);
    z-index: -1;
  }
}
</style>
