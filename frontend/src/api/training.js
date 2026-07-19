import request from '@/utils/request'

export const getTrainingTasks = (params = {}) => request.get('/training/tasks', { params })
export const startTraining = (data) => request.post('/training/start', data)
export const getTrainingStatus = (taskId) => request.get(`/training/status/${taskId}`)
export const getTrainingMetrics = (taskId) => request.get(`/training/metrics/${taskId}`)
export const stopTraining = (taskId) => request.post(`/training/stop/${taskId}`)
export const evaluateTraining = (taskId, data) => request.post(`/training/validate/${taskId}`, data, { timeout: 5 * 60 * 1000 })
export const exportTrainingModel = (taskId, data) => request.post(`/training/export/${taskId}`, data, { timeout: 5 * 60 * 1000 })
export const downloadTrainingResults = (taskUuid) => request.get(`/training/results/${taskUuid}`, { responseType: 'blob' })
export const predictTrainingImage = (formData) => request.post('/training/predict', formData, { timeout: 2 * 60 * 1000 })

export async function downloadTrainingWeights(taskId) {
  const token = localStorage.getItem('rsod_token') || ''
  const response = await fetch(`/api/training/download/${taskId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw new Error(`模型下载失败 (${response.status})`)
  return response.blob()
}
