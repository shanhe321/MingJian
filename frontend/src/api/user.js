/**
 * 用户与权限相关 API 接口
 */
import request from '@/utils/request'

/**
 * 更新当前用户的个人信息
 * @param {Object} data - { email, phone }
 * @returns {Promise} - { message, user }
 */
export function updateProfile(data) {
  return request.put('/user/profile', null, { params: data })
}

/**
 * 修改当前用户密码
 * @param {Object} data - { old_password, new_password }
 * @returns {Promise} - { message }
 */
export function changePassword(data) {
  return request.put('/user/password', null, { params: data })
}

/**
 * 获取用户列表（分页）
 * @param {Object} params - { page, page_size, keyword }
 * @returns {Promise} - { total, page, page_size, items }
 */
export function getUserList(params) {
  return request.get('/user/list', { params })
}

/**
 * 获取系统中所有角色列表
 * @returns {Promise} - { roles: [{ id, name, display_name, description, is_system }] }
 */
export function getRoleList() {
  return request.get('/user/roles')
}
