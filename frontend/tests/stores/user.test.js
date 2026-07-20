import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { getUserInfoApi, logoutApi, isAuthMockEnabled } = vi.hoisted(() => ({
  getUserInfoApi: vi.fn(),
  logoutApi: vi.fn(),
  isAuthMockEnabled: vi.fn(() => false),
}))
vi.mock('@/api/auth', () => ({
  getUserInfoApi,
  loginApi: vi.fn(),
  logoutApi,
}))
vi.mock('@/utils/authMock', async () => {
  const actual = await vi.importActual('@/utils/authMock')
  return {
    ...actual,
    isAuthMockEnabled,
  }
})

import { useUserStore } from '@/stores/user'
import { MOCK_TOKEN } from '@/utils/authMock'

describe('用户 Store 安全退出与角色', () => {
  beforeEach(() => {
    localStorage.clear()
    logoutApi.mockReset()
    getUserInfoApi.mockReset()
    isAuthMockEnabled.mockReturnValue(false)
    setActivePinia(createPinia())
  })

  it('secureLogout 先调用后端再清理本地会话', async () => {
    const store = useUserStore()
    store.token = 'token'
    store.user = { id: 1, roles: ['user'] }
    await store.secureLogout()
    expect(logoutApi).toHaveBeenCalledOnce()
    expect(store.token).toBe('')
    expect(store.user).toBeNull()
  })

  it('roles 中包含 admin 时兼容判定为管理员', () => {
    const store = useUserStore()
    store.user = { roles: ['user', 'admin'], is_superuser: false }
    expect(store.isSuperuser).toBe(true)
  })

  it('auth mock 开启时 login 不打后端且为管理员', async () => {
    isAuthMockEnabled.mockReturnValue(true)
    const store = useUserStore()
    const res = await store.login({ username: 'ui-dev', password: 'any' })
    expect(logoutApi).not.toHaveBeenCalled()
    expect(res.access_token).toBe(MOCK_TOKEN)
    expect(store.token).toBe(MOCK_TOKEN)
    expect(store.username).toBe('ui-dev')
    expect(store.isSuperuser).toBe(true)
  })

  it('auth mock 开启时 fetchUserInfo 失败也不会清空会话', async () => {
    isAuthMockEnabled.mockReturnValue(true)
    const store = useUserStore()
    store.token = MOCK_TOKEN
    store.user = { id: 9, username: 'keep', roles: ['admin'], is_superuser: true }
    await store.fetchUserInfo()
    expect(store.token).toBe(MOCK_TOKEN)
    expect(store.username).toBe('keep')
  })

  it('auth mock 开启时 secureLogout 不调用后端', async () => {
    isAuthMockEnabled.mockReturnValue(true)
    const store = useUserStore()
    store.token = MOCK_TOKEN
    await store.secureLogout()
    expect(logoutApi).not.toHaveBeenCalled()
    expect(store.token).toBe('')
  })

  it('用户信息刷新遇到非鉴权错误时保留本地会话', async () => {
    getUserInfoApi.mockRejectedValue(new Error('service unavailable'))
    const store = useUserStore()
    store.token = 'valid-token'
    store.user = { id: 1, roles: ['user'] }

    await store.fetchUserInfo()

    expect(store.token).toBe('valid-token')
    expect(store.user).toEqual({ id: 1, roles: ['user'] })
  })
})
