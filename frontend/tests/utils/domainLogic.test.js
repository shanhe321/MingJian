import { describe, expect, it } from 'vitest'
import { copyRoles } from '@/utils/roles'
import { getSidebarItems } from '@/utils/navigation'
import { filterModels } from '@/utils/modelFilters'

describe('权限和页面核心逻辑', () => {
  it('角色数组完整复制且不压缩为单值', () => {
    const source = ['user', 'admin', 'future_role']
    const draft = copyRoles(source)
    expect(draft).toEqual(source)
    expect(draft).not.toBe(source)
  })

  it('普通用户导航隐藏管理员入口', () => {
    expect(getSidebarItems(false).some((item) => item.path.startsWith('/admin'))).toBe(false)
  })

  it('管理员导航显示用户权限和审计入口', () => {
    expect(getSidebarItems(true).filter((item) => item.path.startsWith('/admin')).map((item) => item.path))
      .toEqual(['/admin/users', '/admin/audit'])
  })

  it('模型按真实 scene_id 和状态筛选', () => {
    const items = [
      { id: 1, scene_id: 10, status: 'active', version: 'v1.0.0', model_name: 'yolo' },
      { id: 2, scene_id: 20, status: 'archived', version: 'v2.0.0', model_name: 'yolo' },
    ]
    expect(filterModels(items, { keyword: 'v1', scene_id: 10, status: 'active' }).map((item) => item.id)).toEqual([1])
  })
})
