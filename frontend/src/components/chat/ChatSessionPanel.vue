<template>
  <aside class="chat-session-panel" aria-label="Chat 会话侧栏">
    <div class="panel-top">
      <button class="new-session" type="button" @click="startNewChat">
        <el-icon><EditPen /></el-icon>
        <span>新建会话</span>
      </button>
      <el-tooltip content="收起会话侧栏" placement="right">
        <button class="collapse-button" type="button" aria-label="收起会话侧栏" @click="agentStore.toggleSessionPanel(false)">
          <el-icon><DArrowLeft /></el-icon>
        </button>
      </el-tooltip>
    </div>

    <div class="list-heading">
      <strong>最近会话</strong>
      <button type="button" :disabled="agentStore.sessionsLoading" aria-label="刷新会话" @click="refreshSessions">
        <el-icon :class="{ 'is-loading': agentStore.sessionsLoading }"><Refresh /></el-icon>
      </button>
    </div>

    <el-alert
      v-if="agentStore.sessionsError"
      class="session-error"
      type="error"
      :closable="false"
      :title="agentStore.sessionsError"
      show-icon
    />

    <div v-loading="agentStore.sessionsLoading" class="session-list">
      <div
        v-for="session in agentStore.sessions"
        :key="session.session_id"
        class="session-item"
        :class="{ 'is-active': session.session_id === agentStore.currentSessionId }"
      >
        <button class="session-select" type="button" @click="selectSession(session.session_id)">
          <span class="session-icon"><el-icon><ChatLineRound /></el-icon></span>
          <span class="session-copy">
            <strong>{{ session.title || `会话 ${session.session_id}` }}</strong>
            <small>{{ session.updated_at ? formatTime(session.updated_at) : session.session_id }}</small>
          </span>
        </button>
        <button
          type="button"
          class="clear-button"
          aria-label="清空会话"
          @click="clearSession(session)"
        >
          <el-icon><Delete /></el-icon>
        </button>
      </div>

      <div v-if="!agentStore.sessionsLoading && !agentStore.sessions.length" class="empty-sessions">
        <span><el-icon><ChatDotRound /></el-icon></span>
        <strong>暂无历史会话</strong>
        <small>发送第一条消息后，会话会出现在这里。</small>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChatDotRound,
  ChatLineRound,
  DArrowLeft,
  Delete,
  EditPen,
  Refresh,
} from '@element-plus/icons-vue'
import { useAgentStore } from '@/stores/agent'

const router = useRouter()
const agentStore = useAgentStore()

function refreshSessions() {
  agentStore.refreshSessions().catch(() => {})
}

function startNewChat() {
  agentStore.newChat()
  router.push('/chat')
}

async function selectSession(sessionId) {
  try {
    await agentStore.openSession(sessionId)
    await router.push('/chat')
    if (window.innerWidth <= 1100) agentStore.toggleSessionPanel(false)
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '会话内容加载失败')
  }
}

async function clearSession(session) {
  try {
    await ElMessageBox.confirm(
      `确认清空“${session.title || session.session_id}”的会话记忆？`,
      '清空会话',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' },
    )
    await agentStore.clearStoredSession(session.session_id)
    ElMessage.success('会话已清空')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error.response?.data?.detail || '会话清空失败')
    }
  }
}

function formatTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

onMounted(() => {
  if (!agentStore.sessions.length) refreshSessions()
})
</script>

<style lang="scss" scoped>
.chat-session-panel {
  width: 280px;
  min-width: 260px;
  max-width: 300px;
  height: 100%;
  min-height: 0;
  padding: 14px 12px 12px;
  border-right: 1px solid $border-color;
  background: #f8fbff;
  display: flex;
  flex: 0 0 280px;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
  z-index: 70;
}

.panel-top,
.list-heading,
.new-session,
.session-item,
.session-select {
  display: flex;
  align-items: center;
}

.panel-top {
  gap: 7px;
  flex: 0 0 auto;
}

.new-session {
  min-width: 0;
  height: 46px;
  flex: 1;
  justify-content: center;
  gap: 8px;
  padding: 0 14px;
  border: 1px solid rgba(59, 130, 246, 0.24);
  border-radius: 12px;
  background: #eaf4ff;
  color: $primary-color-dark;
  cursor: pointer;
  font-size: 13px;
  font-weight: 650;
  white-space: nowrap;

  span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &:hover {
    border-color: rgba(59, 130, 246, 0.38);
    background: #dfefff;
  }
}

.collapse-button,
.list-heading button {
  display: inline-grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: $text-secondary;
  cursor: pointer;
}

.collapse-button {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  border-radius: 11px;

  &:hover {
    background: #eef7ff;
    color: $text-primary;
  }
}

.list-heading {
  justify-content: space-between;
  flex: 0 0 auto;
  margin: 18px 5px 8px;

  strong {
    color: $text-secondary;
    font-size: 13px;
    font-weight: 650;
  }

  button {
    width: 28px;
    height: 28px;
    border-radius: 8px;

    &:hover:not(:disabled) {
      background: #eef7ff;
      color: $primary-color;
    }
  }
}

.session-error {
  flex: 0 0 auto;
  margin-bottom: 8px;
}

.session-list {
  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 2px;
}

.session-item {
  position: relative;
  width: 100%;
  min-width: 0;
  min-height: 50px;
  margin-bottom: 4px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 11px;
  background: transparent;
  box-sizing: border-box;
  transition: background 0.16s ease, border-color 0.16s ease;

  &:hover,
  &.is-active {
    border-color: rgba(59, 130, 246, 0.14);
    background: #f0f7ff;
  }

  &.is-active {
    background: #eaf4ff;
  }
}

.session-select {
  width: 100%;
  min-width: 0;
  min-height: 48px;
  gap: 9px;
  padding: 7px 36px 7px 8px;
  border: 0;
  border-radius: inherit;
  background: transparent;
  color: $text-regular;
  text-align: left;
  cursor: pointer;
  box-sizing: border-box;
}

.session-icon {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.72);
  color: $primary-color;
}

.session-copy {
  min-width: 0;
  flex: 1;

  strong,
  small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    color: $text-primary;
    font-size: 13px;
    font-weight: 570;
  }

  small {
    margin-top: 3px;
    color: $text-placeholder;
    font-size: 13px;
  }
}

.clear-button {
  position: absolute;
  top: 50%;
  right: 7px;
  display: inline-grid;
  place-items: center;
  width: 27px;
  height: 27px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  color: $text-placeholder;
  cursor: pointer;
  opacity: 0;
  transform: translateY(-50%);
  transition: opacity 0.16s ease, background 0.16s ease;

  .session-item:hover &,
  .session-item:focus-within &,
  &:focus-visible {
    opacity: 1;
  }

  &:hover {
    background: rgba(239, 68, 68, 0.09);
    color: $danger-color;
  }
}

.empty-sessions {
  display: flex;
  min-height: 180px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 18px;
  color: $text-secondary;
  text-align: center;

  > span {
    display: inline-grid;
    place-items: center;
    width: 40px;
    height: 40px;
    margin-bottom: 9px;
    border-radius: 12px;
    background: #eef7ff;
    color: $primary-color;
    font-size: 19px;
  }

  strong { color: $text-primary; font-size: 14px; }
  small { margin-top: 5px; font-size: 13px; line-height: 1.5; }
}

@media (max-width: 1100px) {
  .chat-session-panel {
    position: fixed;
    top: $header-height;
    bottom: 0;
    left: $sidebar-width;
    width: min(280px, calc(100vw - #{$sidebar-width}));
    height: auto;
    box-shadow: 10px 0 28px rgba(37, 99, 235, 0.08);
  }
}
</style>
