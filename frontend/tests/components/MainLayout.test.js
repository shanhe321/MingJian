import { describe, expect, it } from 'vitest'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

describe('主布局视口锁定', () => {
  it('锁定根文档滚动，并使用动态视口高度承载内部滚动区', async () => {
    const layoutSource = (await import('@/components/layout/MainLayout.vue?raw')).default
    const resetSource = await readFile(
      path.resolve(process.cwd(), 'src/assets/styles/reset.scss'),
      'utf8',
    )

    expect(resetSource).toContain('overflow: hidden')
    expect(layoutSource).toContain('height: 100dvh')
    expect(layoutSource).toContain('overflow: hidden')
    expect(layoutSource).toContain('height: calc(100dvh - #{$header-height})')
  })
})
