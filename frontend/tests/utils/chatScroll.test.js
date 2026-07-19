import { describe, expect, it } from 'vitest'
import { CHAT_BOTTOM_THRESHOLD, isNearScrollBottom } from '@/utils/chatScroll'

describe('Chat 自动滚动边界', () => {
  it('用户位于底部阈值内时继续跟随流式输出', () => {
    expect(isNearScrollBottom({ scrollHeight: 1000, scrollTop: 510, clientHeight: 400 })).toBe(true)
  })

  it('用户主动向上滚动超过阈值时停止自动跟随', () => {
    expect(isNearScrollBottom({
      scrollHeight: 1000,
      scrollTop: 500 - CHAT_BOTTOM_THRESHOLD,
      clientHeight: 300,
    })).toBe(false)
  })

  it('尚未渲染消息容器时默认允许跟随', () => {
    expect(isNearScrollBottom(null)).toBe(true)
  })
})
