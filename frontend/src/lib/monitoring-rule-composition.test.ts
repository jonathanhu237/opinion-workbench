import { describe, expect, it } from 'vitest'

import {
  codePointLength,
  composeMonitoringTerms,
  termsFromTextarea,
  trimRuleValue,
} from '@/lib/monitoring-rule-composition'

describe('local monitoring query composition', () => {
  it.each([
    {
      objects: ['龙田街道', '竹坑社区'],
      issues: ['噪音', '积水'],
      expected: [
        '龙田街道 噪音',
        '龙田街道 积水',
        '竹坑社区 噪音',
        '竹坑社区 积水',
      ],
    },
    {
      objects: ['  A  B  ', '旧 完整查询'],
      issues: [],
      expected: ['A  B', '旧 完整查询'],
    },
    { objects: [' Ａ  B '], issues: [' C D '], expected: ['Ａ  B C D'] },
    {
      objects: ['\u0085A B\u001c', '\ufeff完整短语'],
      issues: [],
      expected: ['A B', '\ufeff完整短语'],
    },
    {
      objects: ['𠮷'.repeat(98)],
      issues: ['水'],
      expected: [`${'𠮷'.repeat(98)} 水`],
    },
  ])(
    'matches backend order and full phrases: $expected',
    ({ objects, issues, expected }) => {
      expect(composeMonitoringTerms(objects, issues)).toEqual({
        count: expected.length,
        terms: expected,
      })
    },
  )

  it('splits only lines, ignoring blank lines but preserving embedded spaces', () => {
    expect(termsFromTextarea('  A  B \r\n \n旧 完整查询\n')).toEqual([
      'A  B',
      '旧 完整查询',
    ])
    expect(termsFromTextarea(' \n\r\n ')).toEqual([])
    expect(codePointLength('𠮷'.repeat(100))).toBe(100)
    expect(trimRuleValue('\u0085\u001c 名称 \u001f')).toBe('名称')
    expect(trimRuleValue('\ufeff名称\ufeff')).toBe('\ufeff名称\ufeff')
  })

  it('reports the full oversized count without allocating or truncating the product', () => {
    const generated = composeMonitoringTerms(
      Array.from({ length: 100 }, (_, index) => `对象${index}`),
      Array.from({ length: 100 }, (_, index) => `问题${index}`),
    )
    expect(generated).toEqual({ count: 10000, terms: [] })
  })
})
