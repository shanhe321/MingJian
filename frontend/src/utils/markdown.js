/**
 * Markdown 渲染工具
 * 用于 Day 11 智能体对话中 AI 回复的 Markdown 渲染
 */
import MarkdownIt from 'markdown-it'

// 创建 markdown-it 实例，启用 HTML 支持
const md = new MarkdownIt({
  html: false,        // 禁用 HTML 标签（安全考虑）
  linkify: true,      // 自动将 URL 转为链接
  typographer: true,  // 启用排版优化（如引号替换）
  breaks: false,      // 遵循标准 Markdown：普通换行不强制转为 <br>
})

export function normalizeMarkdownSpacing(text) {
  const lines = String(text ?? '').replace(/\r\n?/g, '\n').split('\n')
  const normalized = []
  let fence = ''
  let pendingBlank = false

  for (const line of lines) {
    const fenceMatch = line.match(/^\s*(`{3,}|~{3,})/)
    if (fenceMatch) {
      const marker = fenceMatch[1][0]
      if (!fence) fence = marker
      else if (fence === marker) fence = ''
      normalized.push(line)
      pendingBlank = false
      continue
    }

    if (fence) {
      normalized.push(line)
      continue
    }

    if (!line.trim()) {
      pendingBlank = normalized.length > 0
      continue
    }

    if (pendingBlank) normalized.push('')
    normalized.push(line)
    pendingBlank = false
  }

  return normalized.join('\n')
}

/**
 * 将 Markdown 文本渲染为 HTML
 * @param {string} text - Markdown 文本
 * @returns {string} 渲染后的 HTML 字符串
 */
export function renderMarkdown(text) {
  if (!text) return ''
  return md.render(normalizeMarkdownSpacing(text))
}

export default md
