import { describe, expect, it } from 'vitest'

import { legacyResultsDestination } from '@/app/router'

describe('legacy results route compatibility', () => {
  it.each([
    ['', { pathname: '/reports', search: '?generate=1' }],
    ['?view=compose', { pathname: '/reports', search: '?generate=1' }],
    ['?result=11', { pathname: '/reports', search: '?result=11&generate=1' }],
    [
      '?view=records&generation=9',
      { pathname: '/reports', search: '?generation=9' },
    ],
    [
      '?report=31&result=11&attempt=4',
      {
        pathname: '/reports',
        search: '?report=31&result=11&attempt=4',
      },
    ],
    ['?job=7', { pathname: '/reports', search: '?job=7' }],
  ])('maps %s to the normalized destination', (search, destination) => {
    expect(legacyResultsDestination(search)).toEqual(destination)
  })

  it.each(['?reports_before=15', '?report_section=501'])(
    'treats legacy report state %s as report records',
    (search) => {
      expect(legacyResultsDestination(search).pathname).toBe('/reports')
    },
  )
})
