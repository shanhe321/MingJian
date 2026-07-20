import { beforeEach, describe, expect, it } from 'vitest'
import {
  TOKEN_KEY,
  buildMockLoginResult,
  ensureMockSession,
  isAuthMockEnabled,
} from '@/utils/authMock'

describe('authMock', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('测试环境默认不启用假登录', () => {
    // vitest 未加载 .env.development 的 VITE_AUTH_MOCK=true
    expect(isAuthMockEnabled()).toBe(false)
    expect(ensureMockSession()).toBe(false)
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('buildMockLoginResult 可覆盖用户名且默认管理员', () => {
    const res = buildMockLoginResult('alice')
    expect(res.access_token).toBeTruthy()
    expect(res.user.username).toBe('alice')
    expect(res.user.is_superuser).toBe(true)
    expect(res.user.roles).toContain('admin')
  })
})
