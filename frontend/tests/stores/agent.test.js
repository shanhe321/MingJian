import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { isReactive } from 'vue'

import { useAgentStore } from '@/stores/agent'

describe('agent store streaming message', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
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
})
