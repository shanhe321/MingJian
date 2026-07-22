import { describe, expect, it } from 'vitest'

describe('DashboardPage 类别分布图', () => {
  it('为窄卡片预留图例空间并隐藏小占比标签', async () => {
    const source = (await import('@/views/DashboardPage.vue?raw')).default

    expect(source).toContain("orient: 'horizontal'")
    expect(source).toContain('data: chartData')
    expect(source).toContain('avoidLabelOverlap: true')
    expect(source).toContain("labelLayout: { hideOverlap: true, moveOverlap: 'shiftY' }")
    expect(source).toContain('params.percent >= 5')
  })
})
