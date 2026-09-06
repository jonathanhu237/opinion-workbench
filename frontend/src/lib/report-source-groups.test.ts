import { describe, expect, it } from 'vitest'
import { resultFixture } from '@/lib/api/analysis-fixtures'
import {
  groupReadingParagraphs,
  groupReportSources,
} from './report-source-groups'

const body =
  '居民反映道路被车辆堵塞，多次投诉后仍然没有解决。消防车辆和救护车辆可能无法进入，居民希望相关部门核实处理。地点为龙田街道老坑社区附近路口，现场情况需要进一步核实，不能将来源的说法直接视作已确认事实。'
function source(id: number, snippet: string) {
  return {
    ...resultFixture({ id }).source,
    result_id: id,
    content_url: `https://m.weibo.cn/detail/${id}`,
    snippet,
  }
}

describe('report source presentation groups', () => {
  it('groups repeated long text despite mentions, spacing and Weibo decorations', () => {
    const first = source(1, `${body} @深圳交警 #龙田街道#深圳交警超话 收起d`)
    const second = source(2, `${body} @坪山发布 #龙田街道#`)
    expect(groupReportSources([first, second])).toEqual([
      { source: first, count: 2, sources: [first, second] },
    ])
  })
  it('preserves different facts, negation, locations and numerical values', () => {
    const values = [
      body,
      body.replace('没有解决', '已经解决'),
      body.replace('老坑', '竹坑'),
      `${body}电费1.5元`,
      `${body}电费15元`,
    ]
    expect(
      groupReportSources(values.map((text, i) => source(i + 1, text))),
    ).toHaveLength(5)
  })
  it('does not merge short or capped previews from different URLs', () => {
    for (const text of ['道路堵塞', '共同开头'.repeat(250)]) {
      expect(
        groupReportSources([source(1, text), source(2, text)]),
      ).toHaveLength(2)
    }
  })
  it('does not mutate source records and always chooses a cited source', () => {
    const sources = [
      Object.freeze(source(1, body)),
      Object.freeze(source(2, body)),
    ]
    const before = JSON.stringify(sources)
    expect(groupReportSources(sources)[0].source).toBe(sources[0])
    expect(JSON.stringify(sources)).toBe(before)
  })
})

describe('report paragraph citation blocks', () => {
  it('consolidates text and media paragraphs with the same source family and preserves all posts', () => {
    const first = source(1, body),
      second = source(2, body),
      third = source(3, body)
    const paragraphs = [
      { text: '堵路投诉', sources: [first, second, third] },
      { text: '现场图片', sources: [first, second] },
      { text: '公厕卫生', sources: [source(4, '公厕卫生问题')] },
      { text: '占道摆卖', sources: [source(5, '摆卖投诉')] },
      { text: '摆卖图片', sources: [source(5, '摆卖投诉')] },
      { text: '执法指控尚待核实', sources: [source(5, '摆卖投诉')] },
    ]
    const before = JSON.stringify(paragraphs)
    const blocks = groupReadingParagraphs(paragraphs)
    expect(blocks.map((block) => block.texts)).toEqual([
      ['堵路投诉', '现场图片'],
      ['公厕卫生'],
      ['占道摆卖', '摆卖图片', '执法指控尚待核实'],
    ])
    expect(blocks[0].groups[0].sources).toEqual([first, second, third])
    expect(blocks[2].groups).toHaveLength(1)
    expect(JSON.stringify(paragraphs)).toBe(before)
  })

  it('does not merge overlapping but different citation sets, unknown legacy citations, or nonadjacent paragraphs', () => {
    const a = source(1, '公厕卫生'),
      b = source(2, '电费问题')
    const paragraphs = [
      { text: '第一段', sources: [a] },
      { text: '两类诉求', sources: [a, b] },
      { text: '第三段', sources: [a] },
      { text: '旧段落1', sources: [] },
      { text: '旧段落2', sources: [] },
    ]
    expect(groupReadingParagraphs(paragraphs)).toHaveLength(5)
  })
})
