import request from '@/utils/request'

export const getScenes = (includeInactive = false) => request.get('/scenes', { params: { include_inactive: includeInactive } })
export const getScene = (id) => request.get(`/scenes/${id}`)
export const createScene = (data) => request.post('/scenes', data)
export const updateScene = (id, data) => request.put(`/scenes/${id}`, data)
export const deleteScene = (id) => request.delete(`/scenes/${id}`)
