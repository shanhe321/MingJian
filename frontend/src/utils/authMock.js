/**
 * 开发态认证 Mock
 * 仅在 Vite DEV + VITE_AUTH_MOCK=true 时生效，生产构建恒为关闭。
 */
export const TOKEN_KEY = 'rsod_token'
export const USER_KEY = 'rsod_user'

export const MOCK_TOKEN = 'dev-mock-token'

export const MOCK_USER = Object.freeze({
  id: 1,
  username: 'dev',
  email: 'dev@example.com',
  avatar: '',
  roles: ['admin', 'user'],
  is_superuser: true,
})

/** 是否启用开发态假登录 */
export function isAuthMockEnabled() {
  return Boolean(import.meta.env.DEV) && import.meta.env.VITE_AUTH_MOCK === 'true'
}

/**
 * 若尚未登录，写入管理员假会话，便于直接浏览内页与管理页。
 * @returns {boolean} 是否写入了新会话
 */
export function ensureMockSession() {
  if (!isAuthMockEnabled()) return false
  if (localStorage.getItem(TOKEN_KEY)) return false

  localStorage.setItem(TOKEN_KEY, MOCK_TOKEN)
  localStorage.setItem(USER_KEY, JSON.stringify(MOCK_USER))
  return true
}

/** 构造一次 mock 登录结果（可覆盖用户名） */
export function buildMockLoginResult(username) {
  const user = {
    ...MOCK_USER,
    username: username?.trim() || MOCK_USER.username,
  }
  return {
    access_token: MOCK_TOKEN,
    token_type: 'bearer',
    user,
  }
}
