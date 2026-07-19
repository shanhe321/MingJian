import { describe, expect, it } from 'vitest'
import { buildTrainingExportPayload } from '@/utils/trainingExport'

const form = { version: ' v1.2.3 ', description: 'test', set_default: true, upload_minio: true }

describe('模型导出权限载荷', () => {
  it('普通用户始终明确提交 set_default=false', () => {
    expect(buildTrainingExportPayload(form, false)).toMatchObject({ version: 'v1.2.3', set_default: false })
  })

  it('管理员可以设置场景默认模型', () => {
    expect(buildTrainingExportPayload(form, true).set_default).toBe(true)
  })
})
