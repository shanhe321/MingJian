import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { routeGuard, routes } from '@/router'
import { useUserStore } from '@/stores/user'

const main = routes.find((route) => route.path === '/')

describe('管理员路由', () => {
  beforeEach(() => {
    localStorage.setItem('rsod_token', 'test-token')
    setActivePinia(createPinia())
  })

  it('/admin 重定向到用户与权限', () => {
    expect(main.children.find((route) => route.path === 'admin').redirect).toBe('/admin/users')
  })

  it('用户与权限、操作审计均要求管理员', () => {
    for (const path of ['admin/users', 'admin/audit']) {
      const route = main.children.find((item) => item.path === path)
      expect(route.meta.requiresAdmin).toBe(true)
      expect(route.meta.sidebarKey).toBe(`/${path}`)
    }
  })

  it('普通用户访问管理员页面时重定向到数据看板', async () => {
    const userStore = useUserStore()
    userStore.user = { id: 1, roles: ['user'], is_superuser: false }
    const next = vi.fn()

    await routeGuard({
      path: '/admin/users',
      fullPath: '/admin/users',
      meta: { title: '用户与权限' },
      matched: [{ meta: { requiresAuth: true } }, { meta: { requiresAdmin: true } }],
    }, {}, next)

    expect(next).toHaveBeenCalledWith('/dashboard')
  })

  it('管理员可以进入用户权限和操作审计页面', async () => {
    const userStore = useUserStore()
    userStore.user = { id: 2, roles: ['user', 'admin'], is_superuser: false }

    for (const path of ['/admin/users', '/admin/audit']) {
      const next = vi.fn()
      await routeGuard({
        path,
        fullPath: path,
        meta: { title: '管理页面' },
        matched: [{ meta: { requiresAuth: true } }, { meta: { requiresAdmin: true } }],
      }, {}, next)
      expect(next).toHaveBeenCalledWith()
    }
  })
})
