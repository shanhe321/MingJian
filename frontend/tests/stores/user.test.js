import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { logoutApi } = vi.hoisted(() => ({ logoutApi: vi.fn() }))
vi.mock('@/api/auth', () => ({
  getUserInfoApi: vi.fn(),
  loginApi: vi.fn(),
  logoutApi,
}))

import { useUserStore } from '@/stores/user'

describe('用户 Store 安全退出与角色', () => {
  beforeEach(() => {
    localStorage.clear()
    logoutApi.mockReset()
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
})
