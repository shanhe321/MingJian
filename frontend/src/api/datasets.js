import request from '@/utils/request'

export const getDatasets = () => request.get('/datasets')
export const getDataset = (id) => request.get(`/datasets/${id}`)

export function createDataset(data) {
  const form = new FormData()
  Object.entries(data).forEach(([key, value]) => value != null && form.append(key, value))
  return request.post('/datasets', form)
}

export function updateDataset(id, data) {
  const form = new FormData()
  Object.entries(data).forEach(([key, value]) => value != null && form.append(key, value))
  return request.put(`/datasets/${id}`, form)
}

export function importDataset(id, file, format) {
  const form = new FormData()
  form.append('file', file)
  form.append('format', format)
  return request.post(`/datasets/${id}/import`, form, { timeout: 10 * 60 * 1000 })
}

export const validateDataset = (id) => request.post(`/datasets/${id}/validate`, null, { timeout: 5 * 60 * 1000 })
export const deleteDataset = (id) => request.delete(`/datasets/${id}`)
