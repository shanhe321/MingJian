export const DEFECT_CLASS_LABELS = Object.freeze({
  missing_hole: '漏孔',
  mouse_bite: '鼠咬',
  open_circuit: '断路',
  short: '短路',
  spur: '毛刺',
  spurious_copper: '多余铜',
})

export function defectClassLabel(className) {
  if (className === null || className === undefined) return ''
  const normalized = String(className)
  return DEFECT_CLASS_LABELS[normalized] || normalized
}

export function compactChartLabel(label, maxLength = 14) {
  const text = String(label ?? '')
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text
}
