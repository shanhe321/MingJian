/**
 * 智能体对话状态管理
 * 管理对话会话列表、当前会话消息等
 */
import { defineStore } from 'pinia'
import {
  clearChatSession,
  getChatSessionHistory,
  getChatSessions,
} from '@/api/chat'
import { createAgentTask, getAgentTaskIdentity } from '@/utils/agentTasks'

export const useAgentStore = defineStore('agent', {
  state: () => ({
    // 当前会话 ID
    currentSessionId: null,

    // 当前会话的消息列表
    messages: [],

    // 会话列表
    sessions: [],

    // 左侧会话面板状态
    sessionPanelOpen: true,
    sessionsLoading: false,
    sessionsError: '',
    sessionLoading: false,
    sessionRequestId: 0,
    focusRequestId: 0,

    // 是否正在等待 AI 响应
    isLoading: false,

    // 当前回复中正在并行执行的 Agent / Tool 任务
    activeAgentTasks: [],

    // 中断函数（用于取消 SSE 流式请求）
    abortController: null,
  }),

  getters: {
    /** 消息数量 */
    messageCount: (state) => state.messages.length,

    /** 是否有会话 */
    hasSession: (state) => state.sessions.length > 0,
  },

  actions: {
    /**
     * 确保当前存在会话 ID，用于对话记忆（Redis 按 session_id 存取历史）
     * 若尚未生成则随机创建一个短 ID
     * @returns {string} 当前会话 ID
     */
    ensureSessionId() {
      if (!this.currentSessionId) {
        this.currentSessionId = Math.random().toString(36).slice(2, 10)
      }
      return this.currentSessionId
    },

    /** 添加一条消息 */
    addMessage(message) {
      this.messages.push(message)
      // 返回 Pinia/Vue 包装后的响应式对象。调用方必须修改该代理，直接修改
      // push 前的原始对象不会触发逐片渲染。
      return this.messages[this.messages.length - 1]
    },

    /** 更新最后一条 AI 消息（用于流式追加） */
    updateLastAssistantMessage(content) {
      const lastMsg = this.messages[this.messages.length - 1]
      if (lastMsg && lastMsg.role === 'assistant') {
        lastMsg.content = content
      }
    },

    /** 设置加载状态 */
    setLoading(loading) {
      this.isLoading = loading
    },

    startAgentTask(event) {
      const identity = getAgentTaskIdentity(event)
      const index = this.activeAgentTasks.findIndex((task) => task.key === identity.key)
      const existing = index >= 0 ? this.activeAgentTasks[index] : null
      const task = createAgentTask(event, existing)
      if (index >= 0) this.activeAgentTasks.splice(index, 1, task)
      else this.activeAgentTasks.push(task)
      return task
    },

    finishAgentTask(event) {
      const identity = getAgentTaskIdentity(event)
      let index = this.activeAgentTasks.findIndex((task) => task.key === identity.key)
      if (index < 0) {
        index = this.activeAgentTasks.findIndex(
          (task) => task.agentName === identity.agentName && task.toolName === identity.toolName,
        )
      }
      if (index >= 0) this.activeAgentTasks.splice(index, 1)
    },

    failAgentTask(event) {
      const identity = getAgentTaskIdentity(event)
      let index = this.activeAgentTasks.findIndex((task) => task.key === identity.key)
      if (index < 0) {
        index = this.activeAgentTasks.findIndex(
          (task) => task.agentName === identity.agentName && task.toolName === identity.toolName,
        )
      }
      if (index >= 0) {
        this.activeAgentTasks[index] = {
          ...this.activeAgentTasks[index],
          status: 'error',
          displayText: event.displayText || event.content || event.message || '执行失败',
        }
      } else {
        this.activeAgentTasks.push(createAgentTask({ ...event, status: 'error' }))
      }
    },

    clearAgentTasks() {
      this.activeAgentTasks = []
    },

    /** 中断当前流式请求 */
    abort() {
      if (this.abortController) {
        this.abortController()
        this.abortController = null
      }
      this.isLoading = false
      this.clearAgentTasks()
    },

    /** 新建对话 */
    newChat() {
      this.abort()
      this.sessionRequestId += 1
      this.currentSessionId = null
      this.messages = []
      this.sessionLoading = false
      this.clearAgentTasks()
      this.requestInputFocus()
    },

    requestInputFocus() {
      this.focusRequestId += 1
    },

    /** 展开或收起左侧会话面板 */
    toggleSessionPanel(force) {
      this.sessionPanelOpen = typeof force === 'boolean' ? force : !this.sessionPanelOpen
    },

    /** 获取当前用户的后端会话列表 */
    async refreshSessions() {
      this.sessionsLoading = true
      this.sessionsError = ''
      try {
        const data = await getChatSessions()
        this.sessions = data.items || (data.sessions || []).map((sessionId) => ({
          session_id: sessionId,
          title: `会话 ${sessionId}`,
        }))
        return this.sessions
      } catch (error) {
        this.sessionsError = '会话列表加载失败，请稍后重试'
        throw error
      } finally {
        this.sessionsLoading = false
      }
    },

    /** 切换到一个后端持久化会话 */
    async openSession(sessionId) {
      if (!sessionId) return
      this.abort()
      const requestId = ++this.sessionRequestId
      this.sessionLoading = true
      this.currentSessionId = sessionId
      this.messages = []
      try {
        const data = await getChatSessionHistory(sessionId)
        if (requestId !== this.sessionRequestId) return
        this.messages = (data.messages || []).map((message, index) => ({
          id: message.id || `history-${sessionId}-${index}`,
          role: message.role === 'ai' ? 'assistant' : message.role,
          content: message.content || '',
          loading: false,
          toolCalls: [],
        }))
      } catch (error) {
        if (requestId === this.sessionRequestId) {
          this.currentSessionId = null
          this.messages = []
        }
        throw error
      } finally {
        if (requestId === this.sessionRequestId) this.sessionLoading = false
      }
    },

    /** 清空一个后端会话，并同步当前会话和列表 */
    async clearStoredSession(sessionId) {
      if (!sessionId) return
      const wasCurrent = this.currentSessionId === sessionId
      if (wasCurrent) {
        this.abort()
        this.sessionRequestId += 1
        this.currentSessionId = null
        this.messages = []
        this.sessionLoading = false
      }
      await clearChatSession(sessionId)
      await this.refreshSessions()
      if (wasCurrent) {
        const nextSession = this.sessions.find((session) => session.session_id !== sessionId)
        if (nextSession) await this.openSession(nextSession.session_id)
        else this.requestInputFocus()
      }
    },

    /** 清除所有状态 */
    clear() {
      this.currentSessionId = null
      this.messages = []
      this.sessions = []
      this.sessionPanelOpen = true
      this.sessionsLoading = false
      this.sessionsError = ''
      this.sessionLoading = false
      this.sessionRequestId += 1
      this.abort()
    },
  },
})
