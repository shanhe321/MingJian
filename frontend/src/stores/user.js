/**
 * 用户状态管理
 * 管理用户登录信息、Token、角色等
 */
import { defineStore } from 'pinia'
import { getUserInfoApi, loginApi, logoutApi } from '@/api/auth'
import {
  TOKEN_KEY,
  USER_KEY,
  buildMockLoginResult,
  isAuthMockEnabled,
} from '@/utils/authMock'

export const useUserStore = defineStore('user', {
  state: () => ({
    // JWT Token
    token: localStorage.getItem(TOKEN_KEY) || '',
    // 用户信息
    user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
  }),

  getters: {
    /** 是否已登录 */
    isLoggedIn: (state) => !!state.token,

    /** 用户名 */
    username: (state) => state.user?.username || '',

    /** 用户头像 */
    avatar: (state) => state.user?.avatar || '',

    /** 用户角色列表 */
    roles: (state) => state.user?.roles || [],

    /** 是否为管理员 */
    isSuperuser: (state) => state.user?.is_superuser || state.user?.roles?.includes('admin') || false,
  },

  actions: {
    /**
     * 用户登录
     * @param {Object} credentials - { username, password }
     */
    async login(credentials) {
      const res = isAuthMockEnabled()
        ? buildMockLoginResult(credentials?.username)
        : await loginApi(credentials)

      // 保存 Token
      this.token = res.access_token
      localStorage.setItem(TOKEN_KEY, res.access_token)

      // 保存用户信息
      this.user = res.user
      localStorage.setItem(USER_KEY, JSON.stringify(res.user))

      return res
    },

    /**
     * 获取最新用户信息
     */
    async fetchUserInfo() {
      if (isAuthMockEnabled()) {
        // 无后端时保留本地假会话，避免 MainLayout / 管理路由把用户踢回登录
        if (!this.token) {
          const mock = buildMockLoginResult()
          this.token = mock.access_token
          this.user = mock.user
          localStorage.setItem(TOKEN_KEY, mock.access_token)
          localStorage.setItem(USER_KEY, JSON.stringify(mock.user))
          return
        }
        if (!this.user) {
          const mock = buildMockLoginResult()
          this.user = mock.user
          localStorage.setItem(USER_KEY, JSON.stringify(mock.user))
        }
        return
      }

      try {
        const user = await getUserInfoApi()
        this.user = user
        localStorage.setItem(USER_KEY, JSON.stringify(user))
      } catch {
        // 仅 401 由请求拦截器清理会话；临时网络或服务错误不应误登出用户。
        return null
      }
    },

    /**
     * 退出登录
     */
    clearSession() {
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },

    logout() {
      this.clearSession()
    },

    async secureLogout() {
      try {
        if (this.token && !isAuthMockEnabled()) await logoutApi()
      } finally {
        this.clearSession()
      }
    },
  },
})
