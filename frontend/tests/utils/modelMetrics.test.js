import { describe, expect, it } from 'vitest'
import { formatMetricPercent, normalizePerClassAp } from '@/utils/modelMetrics'

describe('各类别 AP 规范化', () => {
  it('处理普通对象并映射中文类别', () => {
    expect(normalizePerClassAp({ spur: 0.95, short: 0.91 })).toEqual([
      { className: 'spur', displayName: '毛刺', value: 0.95 },
      { className: 'short', displayName: '短路', value: 0.91 },
    ])
  })

  it('处理 JSON 字符串', () => {
    expect(normalizePerClassAp('{"mouse_bite":0.885}')[0]).toEqual({ className: 'mouse_bite', displayName: '鼠咬', value: 0.885 })
  })

  it('处理数组结构', () => {
    expect(normalizePerClassAp([{ class_name: 'open_circuit', ap: 0.8 }])[0]).toEqual({ className: 'open_circuit', displayName: '断路', value: 0.8 })
  })

  it('处理 API 包装和后端真实 ap50 指标对象', () => {
    expect(normalizePerClassAp({ per_class_ap: { spurious_copper: { ap50: 0.92, ap50_95: 0.67 } } })[0]).toEqual({
      className: 'spurious_copper',
      displayName: '多余铜',
      value: 0.92,
    })
  })

  it('非法字符串、null 和 undefined 安全返回空数组', () => {
    expect(normalizePerClassAp('{invalid')).toEqual([])
    expect(normalizePerClassAp(null)).toEqual([])
    expect(normalizePerClassAp(undefined)).toEqual([])
  })

  it('无效数值不会产生 NaN', () => {
    const [row] = normalizePerClassAp({ spur: { unexpected: true } })
    expect(row.value).toBeNull()
    expect(formatMetricPercent(row.value)).toBe('—')
  })

  it('同时兼容 0～1 与 0～100 数值范围', () => {
    expect(formatMetricPercent(0.952)).toBe('95.20%')
    expect(formatMetricPercent(95.2)).toBe('95.20%')
  })

  it('未知类别保留原始名称', () => {
    expect(normalizePerClassAp({ custom_defect: 0.5 })[0].displayName).toBe('custom_defect')
  })
})
