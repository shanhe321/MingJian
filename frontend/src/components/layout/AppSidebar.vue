<template>
  <aside class="app-sidebar" aria-label="主导航">
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
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  Cpu,
  Clock,
  DataAnalysis,
} from '@element-plus/icons-vue'
import UserAvatarMenu from './UserAvatarMenu.vue'

const route = useRoute()

/** 当前激活的菜单项 */
const activeMenu = computed(() => {
  return '/' + route.path.split('/')[1]
})

/** 侧边栏菜单配置 */
const menuItems = [
  { path: '/training', title: '模型训练', icon: Cpu },
  { path: '/history', title: '历史记录', icon: Clock },
  { path: '/dashboard', title: '数据看板', icon: DataAnalysis },
]
</script>

<style lang="scss" scoped>
.app-sidebar {
  width: $sidebar-width;
  height: 100%;
  background: $sidebar-bg;
  border-right: 1px solid $border-color;
  display: flex;
  flex-direction: column;
  align-items: center;
  overflow: hidden;
}

.sidebar-nav {
  width: 100%;
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: $spacing-md 0;
}

.sidebar-link {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: 1px solid transparent;
  border-radius: $border-radius-md;
  color: $sidebar-text;
  outline: none;
  transition:
    background 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease;

  &:hover,
  &:focus-visible {
    background: rgba(255, 255, 255, 0.06);
    color: $text-primary;
  }

  &:focus-visible {
    border-color: $border-color-strong;
    box-shadow: 0 0 0 2px rgba(167, 139, 250, 0.28);
  }

  &.is-active {
    background: rgba(139, 92, 246, 0.18);
    border-color: rgba(167, 139, 250, 0.32);
    color: $sidebar-active-text;

    &::before {
      content: '';
      position: absolute;
      left: -11px;
      width: 3px;
      height: 20px;
      border-radius: 999px;
      background: linear-gradient(180deg, $primary-color-light, $primary-color);
      box-shadow: 0 0 16px rgba(139, 92, 246, 0.48);
    }
  }
}

.sidebar-icon {
  font-size: 20px;
}

.sidebar-footer {
  width: 100%;
  padding: $spacing-sm 0 $spacing-md;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
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
