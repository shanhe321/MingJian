/**
 * Axios 请求封装
 * - 统一 baseURL 配置
 * - 请求拦截器：自动注入 JWT Token
 * - 响应拦截器：统一错误处理、Token 过期处理
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import router from '@/router'
import { getErrorMessage, isLoginRequest } from '@/utils/errorMessages'

// ── 创建 Axios 实例 ──────────────────────────────────
const request = axios.create({
  baseURL: '/api',          // 配合 Vite proxy，实际请求转发到后端
  timeout: 30000,           // 请求超时 30 秒
  headers: { 'Content-Type': 'application/json' },
})

// ── 请求拦截器 ──────────────────────────────────────
request.interceptors.request.use(
  (config) => {
    // FormData 必须由浏览器生成 multipart boundary。Axios 实例的 JSON
    // 默认头若保留下来，FastAPI Form(...) 将无法读取任何字段。
    if (config.data instanceof FormData) {
      config.headers.delete('Content-Type')
    }

    // 从 Pinia store 获取 Token，自动注入请求头
    const userStore = useUserStore()
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// ── 响应拦截器 ──────────────────────────────────────
request.interceptors.response.use(
  (response) => {
    // 请求成功，直接返回响应数据
    return response.data
  },
  (error) => {
    const message = getErrorMessage(error)
    error.userMessage = message
    ElMessage.error(message)

    if (error.response?.status === 401 && !isLoginRequest(error)) {
      const userStore = useUserStore()
      userStore.clearSession()
      router.push('/login')
    }

    return Promise.reject(error)
  }
)

export default request
