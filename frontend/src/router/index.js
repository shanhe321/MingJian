/**
 * Vue Router 路由配置
 * - 登录/注册页面无需认证
 * - 其他页面需要登录后才能访问
 * - 路由守卫自动检查登录状态
 */
import { createRouter, createWebHistory } from 'vue-router'

// ── 路由定义 ────────────────────────────────────────
export const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginPage.vue'),
    meta: { title: '登录', requiresAuth: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterPage.vue'),
    meta: { title: '注册', requiresAuth: false },
  },

  // ── 需要登录的页面（使用 MainLayout 布局） ──────
  {
    path: '/',
    component: () => import('@/components/layout/MainLayout.vue'),
    redirect: '/chat',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/ChatPage.vue'),
        meta: { title: '智能对话', icon: 'ChatDotRound' },
      },
      {
        path: 'detection',
        name: 'Detection',
        component: () => import('@/views/DetectionPage.vue'),
        meta: { title: '检测工作台', icon: 'Camera' },
      },
      {
        path: 'datasets',
        name: 'Datasets',
        component: () => import('@/views/DatasetsPage.vue'),
        meta: { title: '数据集管理', icon: 'FolderOpened' },
      },
      {
        path: 'training',
        name: 'Training',
        component: () => import('@/views/TrainingPage.vue'),
        meta: { title: '模型训练', icon: 'Cpu' },
      },
      {
        path: 'models',
        name: 'Models',
        component: () => import('@/views/ModelsPage.vue'),
        meta: { title: '模型版本', icon: 'Box' },
      },
      {
        path: 'history',
        name: 'History',
        component: () => import('@/views/HistoryPage.vue'),
        meta: { title: '历史记录', icon: 'Clock' },
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardPage.vue'),
        meta: { title: '数据看板', icon: 'DataAnalysis' },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/SettingsPage.vue'),
        meta: { title: '系统设置', icon: 'Setting' },
      },
      { path: 'admin', redirect: '/admin/users', meta: { requiresAdmin: true } },
      {
        path: 'admin/users',
        name: 'AdminUsers',
        component: () => import('@/views/AdminUsersPage.vue'),
        meta: { title: '用户与权限', icon: 'UserFilled', requiresAdmin: true, sidebarKey: '/admin/users' },
      },
      {
        path: 'admin/audit',
        name: 'AdminAudit',
        component: () => import('@/views/AdminAuditPage.vue'),
        meta: { title: '操作审计', icon: 'Tickets', requiresAdmin: true, sidebarKey: '/admin/audit' },
      },
    ],
  },

  // ── 404 页面 ─────────────────────────────────────
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login',
  },
]

// ── 创建路由实例 ──────────────────────────────────────
const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ── 路由守卫 ────────────────────────────────────────
export async function routeGuard(to, from, next) {
  // 设置页面标题
  document.title = to.meta.title
    ? `${to.meta.title} - PCB 缺陷检测平台`
    : 'PCB 缺陷检测平台'

  // 检查是否需要认证
  const token = localStorage.getItem('rsod_token')
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth !== false)

  if (requiresAuth && !token) {
    // 需要登录但未登录，跳转到登录页
    next({ path: '/login', query: { redirect: to.fullPath } })
  } else if ((to.path === '/login' || to.path === '/register') && token) {
    // 已登录用户访问登录/注册页，跳转到首页
    next('/')
  } else if (to.matched.some((record) => record.meta.requiresAdmin)) {
    const { useUserStore } = await import('@/stores/user')
    const userStore = useUserStore()
    if (!userStore.user) {
      await userStore.fetchUserInfo()
      if (!userStore.user) {
        next({ path: '/login', query: { redirect: to.fullPath } })
        return
      }
    }
    if (userStore.isSuperuser) next()
    else next('/dashboard')
  } else {
    next()
  }
}

router.beforeEach(routeGuard)

export default router
