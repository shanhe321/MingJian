import { describe, expect, it } from 'vitest'
import { normalizeMarkdownSpacing, renderMarkdown } from '@/utils/markdown'

describe('Markdown 标准换行', () => {
  it('普通单次换行不插入 br 或额外空白段落', () => {
    const html = renderMarkdown('第一行\n第二行')
    expect(html).toContain('第一行\n第二行')
    expect(html).not.toContain('<br>')
    expect((html.match(/<p>/g) || [])).toHaveLength(1)
  })

  it('双换行形成一个段落间距', () => {
    const html = renderMarkdown('第一段\n\n第二段')
    expect((html.match(/<p>/g) || [])).toHaveLength(2)
  })

  it('三个以上连续换行压缩为标准双换行', () => {
    expect(normalizeMarkdownSpacing('第一段\n\n\n\n第二段')).toBe('第一段\n\n第二段')
  })

  it('列表结构不被破坏', () => {
    const html = renderMarkdown('- 项目一\n- 项目二')
    expect(html).toContain('<ul>')
    expect((html.match(/<li>/g) || [])).toHaveLength(2)
  })

  it('围栏代码块内部空行保持不变', () => {
    const source = '```js\nconst a = 1\n\n\nconst b = 2\n```'
    expect(normalizeMarkdownSpacing(source)).toBe(source)
    const html = renderMarkdown(source)
    expect(html).toContain('const a = 1\n\n\nconst b = 2')
  })
})
