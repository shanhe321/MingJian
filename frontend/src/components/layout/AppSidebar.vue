<template>
  <aside class="app-sidebar" aria-label="主导航">
    <div class="sidebar-rail">
      <router-link class="brand-mark" to="/chat" aria-label="RSOD 智能检测平台">
        <img :src="rsodLogo" alt="" />
      </router-link>

      <div class="chat-actions" aria-label="Chat 会话操作">
        <el-tooltip content="新建会话" placement="right" :show-after="180">
          <button type="button" class="sidebar-link" aria-label="新建会话" @click="startNewChat">
            <el-icon class="sidebar-icon"><EditPen /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="最近会话" placement="right" :show-after="180">
          <button
            type="button"
            class="sidebar-link"
            :class="{ 'is-active': agentStore.sessionPanelOpen }"
            aria-label="最近会话"
            @click="toggleSessions"
          >
            <el-icon class="sidebar-icon"><ChatDotRound /></el-icon>
            <span v-if="agentStore.sessions.length" class="session-dot"></span>
          </button>
        </el-tooltip>
      </div>

      <span class="rail-divider" aria-hidden="true"></span>

      <nav class="sidebar-nav">
        <el-tooltip
          v-for="item in menuItems"
          :key="item.path"
          :content="item.title"
          placement="right"
          :show-after="180"
        >
          <router-link
            :to="item.path"
            class="sidebar-link"
            :class="{ 'is-active': activeMenu === item.path }"
            :aria-label="item.title"
          >
            <el-icon class="sidebar-icon">
              <component :is="item.icon" />
            </el-icon>
            <span class="sr-only">{{ item.title }}</span>
          </router-link>
        </el-tooltip>
      </nav>

      <div class="sidebar-footer">
        <UserAvatarMenu />
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Box,
  ChatDotRound,
  Clock,
  Cpu,
  DataAnalysis,
  EditPen,
  FolderOpened,
  Tickets,
  UserFilled,
} from '@element-plus/icons-vue'
import UserAvatarMenu from './UserAvatarMenu.vue'
import rsodLogo from '@/assets/images/rsod-logo.png'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import { getSidebarItems } from '@/utils/navigation'

const route = useRoute()
const router = useRouter()
const agentStore = useAgentStore()
const userStore = useUserStore()

const activeMenu = computed(() => route.meta.sidebarKey || '/' + route.path.split('/')[1])
const iconMap = { Box, Cpu, Clock, DataAnalysis, FolderOpened, Tickets, UserFilled }
const menuItems = computed(() => getSidebarItems(userStore.isSuperuser).map((item) => ({
  ...item,
  icon: iconMap[item.icon],
})))

function startNewChat() {
  agentStore.newChat()
  agentStore.toggleSessionPanel(true)
  router.push('/chat')
}

function toggleSessions() {
  if (route.path !== '/chat') {
    agentStore.toggleSessionPanel(true)
    router.push('/chat')
  } else {
    agentStore.toggleSessionPanel()
  }
  if (agentStore.sessionPanelOpen && !agentStore.sessions.length) {
    agentStore.refreshSessions().catch(() => {})
  }
}
</script>

<style lang="scss" scoped>
.app-sidebar {
  width: $sidebar-width;
  min-width: $sidebar-width;
  height: 100%;
  display: flex;
  flex: 0 0 auto;
  overflow: hidden;
  background: #fff;
  z-index: 80;
  box-sizing: border-box;
}

.sidebar-rail {
  width: $sidebar-width;
  min-width: $sidebar-width;
  height: 100%;
  border-right: 1px solid $border-color;
  background: $sidebar-bg;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 6px 0 20px rgba(37, 99, 235, 0.035);
  z-index: 1;
}

.brand-mark {
  display: inline-grid;
  place-items: center;
  width: 42px;
  height: 42px;
  margin-top: 12px;
  border-radius: 14px;
  border: 1px solid $border-color;
  background: #fff;
  box-shadow: none;
  overflow: hidden;

  img {
    width: 40px;
    height: 40px;
    max-width: none;
    object-fit: cover;
    transform: translateX(-3%) scale(1.55);
  }
}

.chat-actions,
.sidebar-nav {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}

.chat-actions {
  padding-top: 16px;
}

.rail-divider {
  width: 26px;
  height: 1px;
  margin: 10px 0 5px;
  background: rgba(148, 163, 184, 0.22);
}

.sidebar-nav {
  flex: 1;
  padding: 0 0 $spacing-sm;
}

.sidebar-link {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: $sidebar-text;
  outline: none;
  cursor: pointer;
  transition: 0.17s ease;

  &:hover,
  &:focus-visible {
    background: #f0f7ff;
    color: $text-primary;
    transform: translateY(-1px);
  }

  &:focus-visible {
    border-color: $border-color-strong;
    box-shadow: none;
  }

  &.is-active {
    border-color: rgba(59, 130, 246, 0.2);
    background: #eaf4ff;
    color: $primary-color-dark;
  }
}

.session-dot {
  position: absolute;
  top: 7px;
  right: 7px;
  width: 5px;
  height: 5px;
  border: 1px solid #fff;
  border-radius: 50%;
  background: $primary-color;
}

.sidebar-icon {
  font-size: 19px;
}

.sidebar-footer {
  width: 100%;
  padding: $spacing-sm 0 $spacing-md;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

</style>
