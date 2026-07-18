import request from '@/utils/request'

export const getModels = (params = {}) => request.get('/training/models', { params })
export const getModel = (id) => request.get(`/training/models/${id}`)
export const setDefaultModel = (id) => request.put(`/training/models/${id}/default`)
export const archiveModel = (id) => request.delete(`/training/models/${id}`)
