import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosHeaders } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { useUserStore } from '@/stores/user'
import request from '@/utils/request'
import router from '@/router'

describe('请求鉴权与错误拦截', () => {
  beforeEach(() => {
    localStorage.clear()
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
})
