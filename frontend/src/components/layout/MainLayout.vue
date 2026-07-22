<template>
  <div class="main-layout">
    <!-- 顶部导航栏 -->
    <AppHeader />

    <!-- 下方区域：侧边栏 + 内容区 -->
    <div class="layout-body">
      <AppSidebar />
      <ChatSessionPanel v-if="showChatSessions" />
      <button
        v-if="showChatSessions"
        type="button"
        class="session-backdrop"
        aria-label="关闭会话侧栏"
        @click="agentStore.toggleSessionPanel(false)"
      ></button>

      <!-- 页面内容区 -->
      <main
        class="layout-content"
        :class="{
          'is-chat-workspace': isChatRoute,
          'is-detect-workspace': isDetectRoute,
        }"
      >
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import ChatSessionPanel from '@/components/chat/ChatSessionPanel.vue'
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const agentStore = useAgentStore()
const userStore = useUserStore()
const isChatRoute = computed(() => route.path === '/chat')
const isDetectRoute = computed(() => route.path === '/detection')
const showChatSessions = computed(() => isChatRoute.value && agentStore.sessionPanelOpen)

onMounted(() => userStore.fetchUserInfo())
</script>

<style lang="scss" scoped>
.main-layout {
  width: 100%;
  height: 100dvh;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: $bg-color-dark;
}

.layout-body {
  flex: 1;
  display: flex;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.layout-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  position: relative;
  isolation: isolate;
  background: $bg-color;
  overflow-y: auto;
  padding: $spacing-lg $spacing-xl;

  &.is-chat-workspace,
  &.is-detect-workspace {
    height: calc(100dvh - #{$header-height});
    min-height: 0;
    overflow: hidden;
    box-sizing: border-box;
  }

  &.is-chat-workspace {
    padding: 0;
  }

  &.is-detect-workspace {
    padding: 12px 16px 14px;
  }

  &::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image:
      linear-gradient(rgba(59, 130, 246, 0.022) 1px, transparent 1px),
      linear-gradient(90deg, rgba(56, 189, 248, 0.02) 1px, transparent 1px);
    background-size: 44px 44px;
    mask-image: radial-gradient(circle at 50% 8%, rgba(0, 0, 0, 0.55), transparent 62%);
    z-index: -1;
  }
}

.session-backdrop {
  display: none;
}

@media (max-width: 1100px) {
  .session-backdrop {
    position: fixed;
    inset: $header-height 0 0 $sidebar-width;
    display: block;
    border: 0;
    background: rgba(32, 45, 72, 0.16);
    backdrop-filter: blur(2px);
    z-index: 68;
  }

  .layout-content.is-detect-workspace {
    overflow-y: auto;
  }
}
</style>
