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
})
