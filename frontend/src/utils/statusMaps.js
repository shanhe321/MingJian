const STATUS_GROUPS = {
  dataset: {
    prepared: { label: '待导入', type: 'info' },
    validating: { label: '校验中', type: 'warning' },
    ready: { label: '可训练', type: 'success' },
    failed: { label: '失败', type: 'danger' },
  },
  detection: {
    pending: { label: '等待中', type: 'info' },
    processing: { label: '处理中', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    failed: { label: '失败', type: 'danger' },
  },
  training: {
    pending: { label: '等待中', type: 'info' },
    running: { label: '训练中', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    failed: { label: '失败', type: 'danger' },
    cancelled: { label: '已取消', type: 'info' },
  },
  model: {
    active: { label: '活跃', type: 'success' },
    archived: { label: '已归档', type: 'info' },
    deleted: { label: '已删除', type: 'danger' },
  },
  risk: {
    low: { label: '低风险', type: 'info' },
    medium: { label: '中风险', type: 'warning' },
    high: { label: '高风险', type: 'danger' },
    none: { label: '无风险', type: 'success' },
  },
  audit: {
    success: { label: '成功', type: 'success' },
    failed: { label: '失败', type: 'danger' },
  },
  evaluation: {
    is_evaluating: { label: '评估中', type: 'warning' },
    is_postprocessing: { label: '后处理中', type: 'warning' },
  },
}

const FALLBACK = { label: '-', type: 'info' }

export function getStatusMeta(group, status) {
  if (status === null || status === undefined || status === '') return FALLBACK
  return STATUS_GROUPS[group]?.[status] || { label: String(status), type: 'info' }
}

export function statusLabel(group, status) {
  return getStatusMeta(group, status).label
}

export function statusType(group, status) {
  return getStatusMeta(group, status).type
}

export { STATUS_GROUPS }
