export function filterModels(items, filters) {
  const keyword = String(filters.keyword || '').trim().toLowerCase()
  return items.filter((row) => {
    const matchesKeyword = !keyword || `${row.version || ''} ${row.model_name || ''}`.toLowerCase().includes(keyword)
    const matchesScene = !filters.scene_id || row.scene_id === filters.scene_id
    const matchesStatus = !filters.status || row.status === filters.status
    return matchesKeyword && matchesScene && matchesStatus
  })
}
