export const CHAT_BOTTOM_THRESHOLD = 96

export function isNearScrollBottom(element, threshold = CHAT_BOTTOM_THRESHOLD) {
  if (!element) return true
  const remaining = element.scrollHeight - element.scrollTop - element.clientHeight
  return remaining <= threshold
}
