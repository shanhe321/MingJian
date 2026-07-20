const ID_FIELDS = ['run_id', 'task_id', 'tool_call_id', 'id']

export function getAgentTaskIdentity(event = {}) {
  const agentName = event.agentName || event.agent_name || event.agent || '智能体'
  const toolName = event.toolName || event.tool_name || event.tool || (event.type === 'thinking' ? 'thinking' : 'task')
  const identifier = ID_FIELDS.map((field) => event[field]).find((value) => value !== undefined && value !== null && value !== '')
  const fallback = `${agentName}:${toolName}`
  return {
    key: identifier === undefined ? fallback : `${identifier}:${toolName}`,
    agentName,
    toolName,
    fallback,
  }
}

export function createAgentTask(event = {}, existing = null, now = Date.now()) {
  const identity = getAgentTaskIdentity(event)
  return {
    key: identity.key,
    agentName: identity.agentName,
    toolName: identity.toolName,
    status: event.status || 'running',
    displayText: event.displayText || event.display_text || event.content || event.message || '正在处理...',
    startTime: existing?.startTime || now,
  }
}
