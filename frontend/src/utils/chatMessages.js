export function composeDetectionUserMessage(message, attachmentSummary) {
  const text = String(message || '').trim()
  return text ? `${text}\n${attachmentSummary}` : attachmentSummary
}
