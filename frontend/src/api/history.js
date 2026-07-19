/**
 * 检测历史记录 API 接口
 */
import request from '@/utils/request'

const REPORT_DOWNLOAD_TIMEOUT_MS = 3 * 60 * 1000

/**
 * 获取检测任务分页列表
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页数量
 * @param {string} [params.task_type] - 任务类型筛选
 * @param {string} [params.status] - 状态筛选
 * @param {number} [params.scene_id] - 场景 ID 筛选
 * @param {string} [params.start_date] - 起始日期
 * @param {string} [params.end_date] - 结束日期
 * @returns {Promise} - { total, page, page_size, total_pages, items }
 */
export function getTaskList(params) {
  return request.get('/history/tasks', { params })
}

/**
 * 获取检测任务详情
 * @param {number} taskId - 任务 ID
 * @returns {Promise} - { task, class_counts, results }
 */
export function getTaskDetail(taskId) {
  return request.get(`/history/tasks/${taskId}`)
}

/**
 * 删除检测任务
 * @param {number} taskId - 任务 ID
 * @returns {Promise} - { message, task_id }
 */
export function deleteTask(taskId) {
  return request.delete(`/history/tasks/${taskId}`)
}

/**
 * 获取历史记录快速统计
 * @returns {Promise} - { total_tasks, today_tasks, status_counts }
 */
export function getHistorySummary() {
  return request.get('/history/summary')
}

/**
 * 获取所有检测场景列表
 * @returns {Promise} - { scenes: [{ id, name, display_name, category }] }
 */
export function getScenes() {
  return request.get('/history/scenes')
}

export function redetectTask(taskId) {
  return request.post(`/history/tasks/${taskId}/redetect`, null, { timeout: 5 * 60 * 1000 })
}

export function downloadReport(taskId) {
  return request.get(`/history/tasks/${taskId}/report.md`, {
    responseType: 'blob',
    timeout: REPORT_DOWNLOAD_TIMEOUT_MS,
  })
}

export function downloadReportArchive(taskId) {
  return request.get(`/history/tasks/${taskId}/report.zip`, {
    responseType: 'blob',
    timeout: REPORT_DOWNLOAD_TIMEOUT_MS,
  })
}
