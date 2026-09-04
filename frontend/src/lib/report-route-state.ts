export function isReportRecordContext(params: URLSearchParams) {
  return (
    params.get('view') === 'records' ||
    params.has('generation') ||
    params.has('report') ||
    params.has('job')
  )
}
