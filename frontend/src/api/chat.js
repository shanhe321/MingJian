/**
 * 对话会话管理相关 API 接口
 *
 * SSE 流式对话本身使用 utils/stream.js 中的 streamChat（fetch + ReadableStream），
 * 这里只封装普通的会话管理接口（列表 / 清空）
 */
import request from '@/utils/request'

export function uploadChatImage(formData) {
  return request.post('/chat/upload', formData, { timeout: 60000 })
}

/**
 * 获取当前用户的历史会话 ID 列表
 * @returns {Promise<{ sessions: string[], items: Array<{session_id:string,title:string}> }>}
 */
export function getChatSessions() {
  return request.get('/chat/sessions')
}

export function getChatSessionHistory(sessionId) {
  return request.get(`/chat/sessions/${sessionId}`)
}

/**
 * 清空指定会话的对话记忆（Redis 中的历史消息）
 * @param {string} sessionId - 会话 ID
 * @returns {Promise<{ message: string }>}
 */
export function clearChatSession(sessionId) {
  return request.post('/chat/clear', { session_id: sessionId })
}
