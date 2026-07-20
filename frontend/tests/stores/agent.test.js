import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { isReactive } from 'vue'

import { clearChatSession, getChatSessionHistory, getChatSessions } from '@/api/chat'
import { useAgentStore } from '@/stores/agent'

vi.mock('@/api/chat', () => ({
  clearChatSession: vi.fn(),
  getChatSessionHistory: vi.fn(),
  getChatSessions: vi.fn(),
}))

describe('agent store streaming message', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('returns the reactive message stored in Pinia', () => {
    const store = useAgentStore()
    const rawMessage = { role: 'assistant', content: '' }

    const storedMessage = store.addMessage(rawMessage)
    storedMessage.content += '第一段'
    storedMessage.content += '第二段'

    expect(isReactive(storedMessage)).toBe(true)
    expect(store.messages[0].content).toBe('第一段第二段')
  })

  it('将会话列表和历史消息标准化为前端共享状态', async () => {
    getChatSessions.mockResolvedValue({ sessions: ['session-a'] })
    getChatSessionHistory.mockResolvedValue({
      messages: [
        { role: 'user', content: '检测这张图片' },
        { role: 'ai', content: '检测完成' },
      ],
    })
    const store = useAgentStore()

    await store.refreshSessions()
    await store.openSession('session-a')

    expect(store.sessions).toEqual([{ session_id: 'session-a', title: '会话 session-a' }])
    expect(store.currentSessionId).toBe('session-a')
    expect(store.messages.map((message) => message.role)).toEqual(['user', 'assistant'])
  })

  it('切换会话时立即清空旧消息并中止旧 SSE', async () => {
    let resolveHistory
    getChatSessionHistory.mockReturnValue(new Promise((resolve) => { resolveHistory = resolve }))
    const store = useAgentStore()
    const abort = vi.fn()
    store.messages = [{ role: 'assistant', content: '旧消息' }]
    store.isLoading = true
    store.abortController = abort

    const switching = store.openSession('session-b')

    expect(abort).toHaveBeenCalledOnce()
    expect(store.messages).toEqual([])
    expect(store.currentSessionId).toBe('session-b')
    expect(store.sessionLoading).toBe(true)

    resolveHistory({ messages: [{ role: 'ai', content: '新消息' }] })
    await switching
    expect(store.messages[0].content).toBe('新消息')
    expect(store.sessionLoading).toBe(false)
  })

  it('新建会话会中止 SSE 并请求输入框聚焦', () => {
    const store = useAgentStore()
    const abort = vi.fn()
    store.currentSessionId = 'session-a'
    store.messages = [{ role: 'user', content: 'hello' }]
    store.isLoading = true
    store.abortController = abort
    const previousFocusRequest = store.focusRequestId

    store.newChat()

    expect(abort).toHaveBeenCalledOnce()
    expect(store.currentSessionId).toBeNull()
    expect(store.messages).toEqual([])
    expect(store.isLoading).toBe(false)
    expect(store.focusRequestId).toBe(previousFocusRequest + 1)
  })

  it('清空当前持久化会话后保留会话数组语义并刷新列表', async () => {
    clearChatSession.mockResolvedValue({ message: 'ok' })
    getChatSessions.mockResolvedValue({ items: [] })
    const store = useAgentStore()
    store.currentSessionId = 'session-a'
    store.messages = [{ role: 'user', content: 'hello' }]

    await store.clearStoredSession('session-a')

    expect(clearChatSession).toHaveBeenCalledWith('session-a')
    expect(store.currentSessionId).toBeNull()
    expect(store.messages).toEqual([])
    expect(store.sessions).toEqual([])
  })

  it('删除当前会话后自动选择下一条可用会话', async () => {
    clearChatSession.mockResolvedValue({ message: 'ok' })
    getChatSessions.mockResolvedValue({ items: [{ session_id: 'session-b', title: '下一条会话' }] })
    getChatSessionHistory.mockResolvedValue({ messages: [{ role: 'ai', content: '下一条消息' }] })
    const store = useAgentStore()
    store.currentSessionId = 'session-a'
    store.messages = [{ role: 'user', content: '待删除消息' }]

    await store.clearStoredSession('session-a')

    expect(store.currentSessionId).toBe('session-b')
    expect(store.messages[0].content).toBe('下一条消息')
  })

  it('连续两个 tool_start 会同时保留并行状态', () => {
    const store = useAgentStore()
    store.startAgentTask({ type: 'tool_start', tool_call_id: 'tool-1', agent: '检测智能体', tool: 'detect_single_image', displayText: '正在检测图片' })
    store.startAgentTask({ type: 'tool_start', tool_call_id: 'tool-2', agent: '分析智能体', tool: 'search_knowledge', displayText: '正在查询知识库' })

    expect(store.activeAgentTasks.map((task) => task.displayText)).toEqual(['正在检测图片', '正在查询知识库'])
  })

  it('一个 tool_end 只移除对应任务', () => {
    const store = useAgentStore()
    store.startAgentTask({ tool_call_id: 'tool-1', agent: '检测智能体', tool: 'detect_single_image' })
    store.startAgentTask({ tool_call_id: 'tool-2', agent: '分析智能体', tool: 'search_knowledge' })
    store.finishAgentTask({ tool_call_id: 'tool-1', agent: '检测智能体', tool: 'detect_single_image' })

    expect(store.activeAgentTasks).toHaveLength(1)
    expect(store.activeAgentTasks[0].toolName).toBe('search_knowledge')
  })

  it('error 只标记对应任务且不清空其他任务', () => {
    const store = useAgentStore()
    store.startAgentTask({ task_id: 'task-1', agent: '检测智能体', tool: 'detect_single_image' })
    store.startAgentTask({ task_id: 'task-2', agent: '分析智能体', tool: 'search_knowledge' })
    store.failAgentTask({ task_id: 'task-1', agent: '检测智能体', tool: 'detect_single_image', message: '检测失败' })

    expect(store.activeAgentTasks).toHaveLength(2)
    expect(store.activeAgentTasks.find((task) => task.toolName === 'detect_single_image')).toMatchObject({ status: 'error', displayText: '检测失败' })
    expect(store.activeAgentTasks.find((task) => task.toolName === 'search_knowledge').status).toBe('running')
  })

  it('done 后清理全部并行任务', () => {
    const store = useAgentStore()
    store.startAgentTask({ run_id: 'run-1', agent: '检测智能体', tool: 'detect_single_image' })
    store.startAgentTask({ run_id: 'run-2', agent: '分析智能体', tool: 'search_knowledge' })
    store.clearAgentTasks()
    expect(store.activeAgentTasks).toEqual([])
  })

  it('旧事件无 ID 时使用 agentName + toolName 兼容匹配', () => {
    const store = useAgentStore()
    store.startAgentTask({ agentName: '分析智能体', toolName: 'search_knowledge', displayText: '正在查询知识库' })
    expect(store.activeAgentTasks[0].key).toBe('分析智能体:search_knowledge')

    store.finishAgentTask({ agentName: '分析智能体', toolName: 'search_knowledge' })
    expect(store.activeAgentTasks).toEqual([])
  })
})
