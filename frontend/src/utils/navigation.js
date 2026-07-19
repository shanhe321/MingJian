const COMMON_ITEMS = [
  { path: '/datasets', title: '数据集管理', icon: 'FolderOpened' },
  { path: '/training', title: '模型训练', icon: 'Cpu' },
  { path: '/models', title: '模型管理', icon: 'Box' },
  { path: '/history', title: '历史记录', icon: 'Clock' },
  { path: '/dashboard', title: '数据看板', icon: 'DataAnalysis' },
]

const ADMIN_ITEMS = [
  { path: '/admin/users', title: '用户与权限', icon: 'UserFilled' },
  { path: '/admin/audit', title: '操作审计', icon: 'Tickets' },
]

export function getSidebarItems(isAdmin) {
  return [...COMMON_ITEMS, ...(isAdmin ? ADMIN_ITEMS : [])]
}
