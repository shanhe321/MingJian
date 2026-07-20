import { defectClassLabel } from '@/utils/defectClasses'

function parseInput(input) {
  if (typeof input !== 'string') return input
  const value = input.trim()
  if (!value) return null
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function finiteMetric(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function metricFromEntry(entry) {
  if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
    return finiteMetric(entry.ap ?? entry.ap50 ?? entry.value ?? entry.map50)
  }
  return finiteMetric(entry)
}

function normalizedRow(className, rawValue) {
  if (className === null || className === undefined || className === '') return null
  const normalizedName = String(className)
  return {
    className: normalizedName,
    displayName: defectClassLabel(normalizedName),
    value: metricFromEntry(rawValue),
  }
}

export function normalizePerClassAp(input) {
  let value = parseInput(input)
  if (!value) return []

  if (!Array.isArray(value) && typeof value === 'object' && 'per_class_ap' in value) {
    value = parseInput(value.per_class_ap)
  }
  if (!value) return []

  if (Array.isArray(value)) {
    return value
      .map((entry) => normalizedRow(
        entry?.class_name ?? entry?.className ?? entry?.name,
        entry,
      ))
      .filter(Boolean)
  }

  if (typeof value === 'object') {
    return Object.entries(value)
      .map(([className, metric]) => normalizedRow(className, metric))
      .filter(Boolean)
  }

  return []
}

export function formatMetricPercent(value) {
  const metric = finiteMetric(value)
  if (metric === null) return '—'
  const percent = Math.abs(metric) <= 1 ? metric * 100 : metric
  return `${percent.toFixed(2)}%`
}
