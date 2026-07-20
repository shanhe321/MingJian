import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosHeaders } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import request from '@/utils/request'
import router from '@/router'

const { isAuthMockEnabled } = vi.hoisted(() => ({
  isAuthMockEnabled: vi.fn(() => false),
}))
vi.mock('@/utils/authMock', async () => {
  const actual = await vi.importActual('@/utils/authMock')
  return {
    ...actual,
    isAuthMockEnabled,
  }
})

describe('请求鉴权与错误拦截', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    isAuthMockEnabled.mockReturnValue(false)
    setActivePinia(createPinia())
  })

  it('FormData 删除 JSON Content-Type 并保留 Bearer Token', () => {
    const store = useUserStore()
    store.token = 'jwt-token'
    const handler = request.interceptors.request.handlers[0].fulfilled
    const config = handler({ data: new FormData(), headers: new AxiosHeaders({ 'Content-Type': 'application/json' }) })
    expect(config.headers.get('Content-Type')).toBeUndefined()
    expect(config.headers.get('Authorization')).toBe('Bearer jwt-token')
  })

  it('401 清理会话并跳转登录页', async () => {
    const store = useUserStore()
    store.token = 'expired'
    store.user = { id: 1, roles: ['user'] }
    const pushSpy = vi.spyOn(router, 'push').mockResolvedValue()
    const handler = request.interceptors.response.handlers[0].rejected
    const error = { response: { status: 401, data: { detail: 'expired' } } }
    await expect(handler(error)).rejects.toBe(error)
    expect(store.token).toBe('')
    expect(store.user).toBeNull()
    expect(pushSpy).toHaveBeenCalledWith('/login')
    pushSpy.mockRestore()
  })

  it('auth mock 开启时 401 不清理会话', async () => {
    isAuthMockEnabled.mockReturnValue(true)
    const store = useUserStore()
    store.token = 'dev-mock-token'
    store.user = { id: 1, roles: ['admin'], is_superuser: true }
    const pushSpy = vi.spyOn(router, 'push').mockResolvedValue()
    const handler = request.interceptors.response.handlers[0].rejected
    const error = { response: { status: 401, data: { detail: 'expired' } } }
    await expect(handler(error)).rejects.toBe(error)
    expect(store.token).toBe('dev-mock-token')
    expect(store.user).not.toBeNull()
    expect(pushSpy).not.toHaveBeenCalled()
    pushSpy.mockRestore()
  })

  it('登录接口 401 提示用户名或密码错误且不清理已有会话', async () => {
    const store = useUserStore()
    store.token = 'existing-token'
    store.user = { id: 1, roles: ['user'] }
    const pushSpy = vi.spyOn(router, 'push').mockResolvedValue()
    const handler = request.interceptors.response.handlers[0].rejected
    const error = {
      config: { url: '/auth/login' },
      response: { status: 401, data: { detail: 'Unauthorized' } },
    }

    await expect(handler(error)).rejects.toBe(error)
    expect(error.userMessage).toBe('用户名或密码错误')
    expect(ElMessage.error).toHaveBeenCalledWith('用户名或密码错误')
    expect(store.token).toBe('existing-token')
    expect(store.user).toEqual({ id: 1, roles: ['user'] })
    expect(pushSpy).not.toHaveBeenCalled()
    pushSpy.mockRestore()
  })

  it('403 优先显示后端停用提示且保留登录状态', async () => {
    const store = useUserStore()
    store.token = 'valid-token'
    const handler = request.interceptors.response.handlers[0].rejected
    const error = {
      config: { url: '/auth/me' },
      response: { status: 403, data: { detail: '用户已停用，请联系管理员' } },
    }

    await expect(handler(error)).rejects.toBe(error)
    expect(error.userMessage).toBe('用户已停用，请联系管理员')
    expect(ElMessage.error).toHaveBeenCalledWith('用户已停用，请联系管理员')
    expect(store.token).toBe('valid-token')
  })
})
