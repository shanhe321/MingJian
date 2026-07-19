import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/request', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

import request from '@/utils/request'
import { createDataset, importDataset, validateDataset } from '@/api/datasets'

describe('数据集 API 参数', () => {
  beforeEach(() => vi.clearAllMocks())

  it('创建数据集使用后端 Form 字段', () => {
    createDataset({ name: 'PCB', scene_id: 3, description: 'desc' })
    const [path, form] = request.post.mock.calls[0]
    expect(path).toBe('/datasets')
    expect(Object.fromEntries(form.entries())).toEqual({ name: 'PCB', scene_id: '3', description: 'desc' })
  })

  it('导入保持 file 和 format 字段', () => {
    const file = new File(['zip'], 'dataset.zip', { type: 'application/zip' })
    importDataset(8, file, 'coco')
    const [path, form] = request.post.mock.calls[0]
    expect(path).toBe('/datasets/8/import')
    expect(form.get('file')).toBe(file)
    expect(form.get('format')).toBe('coco')
  })

  it('校验调用真实 validate 路径', () => {
    validateDataset(9)
    expect(request.post).toHaveBeenCalledWith('/datasets/9/validate', null, expect.objectContaining({ timeout: expect.any(Number) }))
  })
})
