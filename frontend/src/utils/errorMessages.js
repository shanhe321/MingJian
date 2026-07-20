const LOGIN_PATH = '/auth/login'

function responseMessage(data) {
  const detail = data?.detail
  if (Array.isArray(detail)) return detail[0]?.msg || detail[0]?.message || ''
  if (typeof detail === 'string') return detail
  if (typeof data?.message === 'string') return data.message
  return ''
}

export function isLoginRequest(error) {
  const url = error?.config?.url || error?.response?.config?.url || ''
  return url.split('?')[0].endsWith(LOGIN_PATH)
}

export function getErrorMessage(error) {
  if (error?.code === 'ECONNABORTED' || /timeout/i.test(error?.message || '')) {
    return '网络连接超时，请稍后重试'
  }

  const status = error?.response?.status
  const backendMessage = responseMessage(error?.response?.data)

  if (status === 401) {
    return isLoginRequest(error) ? '用户名或密码错误' : '登录已过期，请重新登录'
  }
  if (status === 403) return backendMessage || '没有权限执行此操作'
  if (status === 502 || status === 503) return '后端服务暂不可用，请稍后重试'
  if (backendMessage) return backendMessage
  if (!error?.response && error?.request) return '后端服务暂不可用，请稍后重试'
  return '操作失败，请稍后重试'
}

