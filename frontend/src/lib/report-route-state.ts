export function isReportRecordContext(params: URLSearchParams) {
  return (
    params.get('view') === 'records' ||
    params.has('generation') ||
    params.has('report') ||
    params.has('job') ||
    params.has('reports_before') ||
    params.has('report_section') ||
    params.has('report_sources_offset') ||
    params.has('report_sections_offset')
  )
}
