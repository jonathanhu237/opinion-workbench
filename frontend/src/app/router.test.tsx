import { describe, expect, it } from 'vitest'

import { legacyResultsDestination } from '@/app/router'

describe('legacy results route compatibility', () => {
  it.each([
    ['', { pathname: '/reports/new', search: '' }],
    ['?view=compose', { pathname: '/reports/new', search: '' }],
    ['?result=11', { pathname: '/reports/new', search: '?result=11' }],
    [
      '?view=records&generation=9',
      { pathname: '/reports/history', search: '?generation=9' },
    ],
    [
      '?report=31&result=11&attempt=4',
      {
        pathname: '/reports/history',
        search: '?report=31&result=11&attempt=4',
      },
    ],
    ['?job=7', { pathname: '/reports/history', search: '?job=7' }],
  ])('maps %s to the normalized destination', (search, destination) => {
    expect(legacyResultsDestination(search)).toEqual(destination)
  })

  it.each(['?reports_before=15', '?report_section=501'])(
    'treats legacy report state %s as report records',
    (search) => {
      expect(legacyResultsDestination(search).pathname).toBe('/reports/history')
    },
  )
})
