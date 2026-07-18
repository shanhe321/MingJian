import request from '@/utils/request'

export const getHealth = () => request.get('/health')
export const getHealthDetail = () => request.get('/health/detail')
export const getRedisSummary = () => request.get('/health/redis')
export const getRedisInfo = () => request.get('/health/redis/info')

export const getKnowledgeStats = () => request.get('/knowledge/stats')
export const rebuildKnowledge = (forceRebuild = true) => request.post('/knowledge/build', null, { params: { force_rebuild: forceRebuild } })
export const searchKnowledge = (query, topK = 3) => request.post('/knowledge/search', { query, top_k: topK })
