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
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(246, 249, 255, 0.76)),
    $sidebar-bg;
  border-right: 1px solid $border-color;
  display: flex;
  flex-direction: column;
  align-items: center;
  overflow: hidden;
  box-shadow: 10px 0 32px rgba(40, 58, 96, 0.05);
  backdrop-filter: blur(18px) saturate(1.08);
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
    background:
      linear-gradient(135deg, rgba(91, 124, 250, 0.1), rgba(139, 92, 246, 0.08));
    color: $text-primary;
    transform: translateY(-1px);
  }

  &:focus-visible {
    border-color: $border-color-strong;
    box-shadow: 0 0 0 2px rgba(91, 124, 250, 0.16);
  }

  &.is-active {
    background:
      linear-gradient(135deg, rgba(91, 124, 250, 0.18), rgba(139, 92, 246, 0.14)),
      rgba(255, 255, 255, 0.76);
    border-color: rgba(91, 124, 250, 0.24);
    color: $sidebar-active-text;
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.74),
      0 10px 24px rgba(91, 124, 250, 0.14);

    &::before {
      content: '';
      position: absolute;
      left: -11px;
      width: 3px;
      height: 20px;
      border-radius: 999px;
      background: linear-gradient(180deg, $primary-color-light, $primary-color);
      box-shadow: 0 0 14px rgba(91, 124, 250, 0.26);
    }
  }
}

.sidebar-icon {
  font-size: 20px;
}

.sidebar-footer {
  width: 100%;
  padding: $spacing-sm 0 $spacing-md;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  background: linear-gradient(180deg, transparent, rgba(91, 124, 250, 0.035));
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
