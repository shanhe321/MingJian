import request from '@/utils/request'

export const getAuditLogs = (params = {}) => request.get('/audit/logs', { params })
