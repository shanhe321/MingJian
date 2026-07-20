<template>
  <div class="user-avatar-menu">
    <el-dropdown
      trigger="click"
      placement="right-end"
      popper-class="rsod-dark-popper user-menu-popper"
      @command="handleCommand"
    >
      <button
        type="button"
        class="avatar-trigger"
        :aria-label="`打开用户菜单：${displayName}`"
        title="用户菜单"
      >
        <el-avatar :size="38" :src="userStore.avatar || undefined" class="letter-avatar">
          {{ userInitial }}
        </el-avatar>
      </button>

      <template #dropdown>
        <el-dropdown-menu>
          <div class="avatar-menu-header">
            <strong>{{ displayName }}</strong>
            <small>{{ roleText }}</small>
          </div>
          <el-dropdown-item command="settings">
            <el-icon><Setting /></el-icon>系统设置
          </el-dropdown-item>
          <el-dropdown-item command="logout" divided>
            <el-icon><SwitchButton /></el-icon>退出登录
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Setting, SwitchButton } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const displayName = computed(() => userStore.username || 'User')
const userInitial = computed(() => displayName.value.charAt(0).toUpperCase())
const roleText = computed(() => {
  const labels = { admin: '管理员', user: '普通用户' }
  const roles = userStore.roles.map((role) => labels[role] || role)
  return roles.length ? roles.join(' · ') : '未分配角色'
})

async function handleCommand(command) {
  switch (command) {
    case 'settings':
      router.push('/settings')
      break
    case 'logout':
      try {
        await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning',
        })
        await userStore.secureLogout()
        await router.push('/login')
      } catch {
        // 用户取消退出时保持当前会话。
      }
      break
  }
}
</script>

<style lang="scss" scoped>
.user-avatar-menu {
  display: flex;
  justify-content: center;
  width: 100%;
}

.avatar-menu-header {
  min-width: 180px;
  padding: 10px 14px 9px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
  margin-bottom: 4px;

  strong,
  small {
    display: block;
  }

  strong {
    color: $text-primary;
    font-size: 13px;
    line-height: 1.4;
  }

  small {
    color: $text-secondary;
    font-size: 12px;
    line-height: 1.5;
  }
}

.avatar-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  cursor: pointer;
  transition:
    background 0.18s ease,
    border-color 0.18s ease,
    transform 0.18s ease;

  &:hover,
  &:focus-visible {
    border-color: $border-color-strong;
    background: #f0f7ff;
    transform: translateY(-1px);
    outline: none;
  }

  &:focus-visible {
    box-shadow: none;
  }
}

.letter-avatar {
  --el-avatar-bg-color: transparent;
  background: #3b82f6;
  color: #fff;
  font-weight: 700;
  box-shadow: none;
}
</style>
