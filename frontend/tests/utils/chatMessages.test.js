import { describe, expect, it } from 'vitest'
import { composeDetectionUserMessage } from '@/utils/chatMessages'

describe('检测用户消息', () => {
  it.each([
    ['批量图片', '[批量检测] 3 张图片'],
    ['ZIP', '[ZIP 检测] boards.zip'],
    ['文件夹', '[文件夹检测] 8 张图片'],
    ['视频', '[视频检测] board.mp4 (4.2MB)'],
  ])('%s 检测保留用户输入并追加附件摘要', (_, summary) => {
    expect(composeDetectionUserMessage('请重点检查短路', summary)).toBe(
      `请重点检查短路\n${summary}`,
    )
  })

  it('没有输入文字时只显示附件摘要', () => {
    expect(composeDetectionUserMessage('', '[批量检测] 2 张图片')).toBe('[批量检测] 2 张图片')
  })
})
