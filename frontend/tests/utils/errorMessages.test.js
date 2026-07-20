import { describe, expect, it } from 'vitest'
import { getErrorMessage, isLoginRequest } from '@/utils/errorMessages'

describe('统一网络错误文案', () => {
  it('识别登录请求并区分登录 401 与会话 401', () => {
    const loginError = { config: { url: '/auth/login?source=web' }, response: { status: 401 } }
    const sessionError = { config: { url: '/auth/me' }, response: { status: 401 } }

    expect(isLoginRequest(loginError)).toBe(true)
    expect(getErrorMessage(loginError)).toBe('用户名或密码错误')
    expect(getErrorMessage(sessionError)).toBe('登录已过期，请重新登录')
  })

  it.each([502, 503])('将 %s 归类为后端服务暂不可用', (status) => {
    expect(getErrorMessage({ response: { status } })).toBe('后端服务暂不可用，请稍后重试')
  })

  it('区分超时、网络不可达和未知错误', () => {
    expect(getErrorMessage({ code: 'ECONNABORTED', message: 'timeout of 30000ms exceeded' })).toBe('网络连接超时，请稍后重试')
    expect(getErrorMessage({ request: {} })).toBe('后端服务暂不可用，请稍后重试')
    expect(getErrorMessage(new Error('unexpected'))).toBe('操作失败，请稍后重试')
  })

  it('普通业务错误优先使用后端 detail 或 message', () => {
    expect(getErrorMessage({ response: { status: 422, data: { detail: '场景参数无效' } } })).toBe('场景参数无效')
    expect(getErrorMessage({ response: { status: 400, data: { message: '任务无法启动' } } })).toBe('任务无法启动')
    expect(getErrorMessage({ response: { status: 422, data: { detail: [{ msg: '字段不能为空' }] } } })).toBe('字段不能为空')
  })

  it('403 优先使用后端用户停用文案', () => {
    expect(getErrorMessage({ response: { status: 403, data: { detail: '用户已停用，请联系管理员' } } })).toBe('用户已停用，请联系管理员')
  })
})
