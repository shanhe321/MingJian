import { describe, expect, it } from 'vitest'
import { getStatusMeta, statusLabel, statusType } from '@/utils/statusMaps'

describe('统一业务状态映射', () => {
  it.each([
    ['dataset', 'prepared', '待导入'],
    ['dataset', 'validating', '校验中'],
    ['detection', 'processing', '处理中'],
    ['training', 'cancelled', '已取消'],
    ['model', 'archived', '已归档'],
    ['risk', 'high', '高风险'],
    ['audit', 'success', '成功'],
    ['evaluation', 'is_postprocessing', '后处理中'],
  ])('%s/%s 显示为 %s', (group, status, label) => {
    expect(statusLabel(group, status)).toBe(label)
    expect(statusType(group, status)).toBeTruthy()
  })

  it('未知后端状态原样展示而不伪造含义', () => {
    expect(getStatusMeta('training', 'future_state')).toEqual({ label: 'future_state', type: 'info' })
  })
})
