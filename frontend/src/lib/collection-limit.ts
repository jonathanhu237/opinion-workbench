export function collectionLimitLabel(value: {
  max_results_per_term: number
  max_total_results?: number | null
}) {
  return value.max_total_results != null
    ? `最新优先 · 合计最多 ${value.max_total_results} 条`
    : `每词最多 ${value.max_results_per_term} 条（旧配置）`
}
