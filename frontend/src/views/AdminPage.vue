<template>
  <div>
    <div class="page-header"><h2>系统管理</h2><el-button @click="loadAll">刷新</el-button></div>
    <el-tabs>
      <el-tab-pane label="用户与角色">
        <el-table :data="users" v-loading="loading">
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="email" label="邮箱" />
          <el-table-column label="账号状态" width="120">
            <template #default="{ row }">
              <el-switch
                :model-value="row.is_active"
                inline-prompt
                active-text="启用"
                inactive-text="停用"
                @change="(value) => saveStatus(row, value)"
              />
            </template>
          </el-table-column>
          <el-table-column label="角色" width="220">
            <template #default="{ row }">
              <el-select v-model="roleDraft[row.id]" style="width: 130px">
                <el-option v-for="role in roles" :key="role.name" :label="role.display_name" :value="role.name" />
              </el-select>
              <el-button type="primary" link @click="saveRole(row)">保存</el-button>
            </template>
          </el-table-column>
          <el-table-column prop="last_login_at" label="最后登录" min-width="180" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="检测场景">
        <el-button type="primary" style="margin-bottom: 12px" @click="openScene()">新增场景</el-button>
        <el-table :data="scenes">
          <el-table-column prop="name" label="标识" />
          <el-table-column prop="display_name" label="名称" />
          <el-table-column prop="category" label="分类" />
          <el-table-column label="类别数"><template #default="{ row }">{{ row.class_names.length }}</template></el-table-column>
          <el-table-column label="状态"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button link @click="showSceneDetail(row)">详情</el-button>
              <el-button link type="primary" @click="openScene(row)">编辑</el-button>
              <el-button link type="danger" @click="removeScene(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="审计日志">
        <el-table :data="logs" size="small">
          <el-table-column prop="created_at" label="时间" min-width="180" />
          <el-table-column prop="username" label="用户" />
          <el-table-column prop="module" label="模块" />
          <el-table-column prop="action" label="操作" />
          <el-table-column prop="status" label="状态" />
          <el-table-column prop="description" label="说明" min-width="220" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="系统与知识库">
        <div class="toolbar">
          <el-button type="primary" @click="loadSystem">刷新状态</el-button>
          <el-button type="warning" :loading="rebuilding" @click="handleRebuildKnowledge">重建知识库</el-button>
        </div>
        <el-descriptions :column="2" border style="margin-bottom: 16px">
          <el-descriptions-item label="应用状态">{{ health?.data?.status || '-' }}</el-descriptions-item>
          <el-descriptions-item label="应用版本">{{ health?.data?.version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="PostgreSQL">{{ serviceStatus('database') }}</el-descriptions-item>
          <el-descriptions-item label="Redis">{{ serviceStatus('redis') }}</el-descriptions-item>
          <el-descriptions-item label="MinIO">{{ serviceStatus('minio') }}</el-descriptions-item>
          <el-descriptions-item label="Redis Key 数">{{ redisSummary?.data?.key_count ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="Redis 模式">{{ redisInfo?.data?.use_redis === false ? '内存降级' : 'Redis' }}</el-descriptions-item>
          <el-descriptions-item label="知识片段数">{{ knowledgeStats?.total_chunks ?? knowledgeStats?.count ?? 0 }}</el-descriptions-item>
        </el-descriptions>
        <el-form inline @submit.prevent>
          <el-form-item label="知识库检索">
            <el-input v-model="knowledgeQuery" placeholder="输入 PCB 缺陷问题" style="width: 320px" @keyup.enter="handleKnowledgeSearch" />
          </el-form-item>
          <el-form-item><el-button type="primary" @click="handleKnowledgeSearch">测试检索</el-button></el-form-item>
        </el-form>
        <el-table v-if="knowledgeResults.length" :data="knowledgeResults" size="small">
          <el-table-column prop="source" label="来源" width="180" />
          <el-table-column prop="content" label="匹配内容" min-width="360" show-overflow-tooltip />
          <el-table-column prop="score" label="相似度" width="100" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="sceneDialog" :title="sceneForm.id ? '编辑场景' : '新增场景'" width="620px">
      <el-form :model="sceneForm" label-width="100px">
        <el-form-item label="场景标识"><el-input v-model="sceneForm.name" :disabled="!!sceneForm.id" /></el-form-item>
        <el-form-item label="显示名称"><el-input v-model="sceneForm.display_name" /></el-form-item>
        <el-form-item label="分类"><el-input v-model="sceneForm.category" /></el-form-item>
        <el-form-item label="英文类别"><el-input v-model="sceneForm.classNamesText" type="textarea" placeholder="short,open_circuit" /></el-form-item>
        <el-form-item label="中文映射"><el-input v-model="sceneForm.classNamesCnText" type="textarea" placeholder='{"short":"短路"}' /></el-form-item>
        <el-form-item label="描述"><el-input v-model="sceneForm.description" type="textarea" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="sceneForm.is_active" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="sceneDialog=false">取消</el-button><el-button type="primary" @click="saveScene">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="sceneDetailDialog" title="场景详情" width="620px">
      <el-descriptions v-if="sceneDetail" :column="1" border>
        <el-descriptions-item label="场景标识">{{ sceneDetail.name }}</el-descriptions-item>
        <el-descriptions-item label="显示名称">{{ sceneDetail.display_name }}</el-descriptions-item>
        <el-descriptions-item label="分类">{{ sceneDetail.category }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ sceneDetail.is_active ? '启用' : '停用' }}</el-descriptions-item>
        <el-descriptions-item label="英文类别">{{ sceneDetail.class_names?.join(', ') }}</el-descriptions-item>
        <el-descriptions-item label="中文类别">{{ Object.values(sceneDetail.class_names_cn || {}).join('、') }}</el-descriptions-item>
        <el-descriptions-item label="说明">{{ sceneDetail.description || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { getAuditLogs } from '@/api/audit'
import { createScene, deleteScene, getScene, getScenes, updateScene } from '@/api/scenes'
import { getHealth, getHealthDetail, getKnowledgeStats, getRedisInfo, getRedisSummary, rebuildKnowledge, searchKnowledge } from '@/api/system'
import { getRoleList, getUserList, setUserRoles, setUserStatus } from '@/api/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

const loading = ref(false); const users = ref([]); const scenes = ref([]); const logs = ref([]); const roles = ref([])
const roleDraft = reactive({}); const sceneDialog = ref(false)
const sceneDetailDialog = ref(false); const sceneDetail = ref(null)
const health = ref(null); const healthDetail = ref(null); const redisSummary = ref(null); const redisInfo = ref(null)
const knowledgeStats = ref(null); const knowledgeQuery = ref(''); const knowledgeResults = ref([]); const rebuilding = ref(false)
const sceneForm = reactive({ id: null, name: '', display_name: '', category: 'industry', classNamesText: '', classNamesCnText: '{}', description: '', is_active: true })

async function loadAll() {
  loading.value = true
  try {
    const [userRes, sceneRes, auditRes, roleRes] = await Promise.all([getUserList({ page: 1, page_size: 100 }), getScenes(true), getAuditLogs({ page: 1, page_size: 100 }), getRoleList()])
    users.value = userRes.items || []; scenes.value = sceneRes.items || []; logs.value = auditRes.items || []; roles.value = roleRes.roles || []
    users.value.forEach((user) => { roleDraft[user.id] = user.roles.includes('admin') ? 'admin' : 'user' })
  } finally { loading.value = false }
}
async function saveRole(row) { await setUserRoles(row.id, [roleDraft[row.id]]); ElMessage.success('角色已更新'); await loadAll() }
async function saveStatus(row, value) {
  try {
    await setUserStatus(row.id, value)
    ElMessage.success(value ? '用户已启用' : '用户已停用')
  } catch {
    // 接口错误由公共请求层提示，重新加载以恢复开关的真实状态。
  } finally {
    await loadAll()
  }
}
async function showSceneDetail(row) { sceneDetail.value = await getScene(row.id); sceneDetailDialog.value = true }
function serviceStatus(name) { const item=healthDetail.value?.data?.services?.[name]; return item ? `${item.status}：${item.message}` : '-' }
async function loadSystem() {
  try {
    const [basic, detail, redis, info, knowledge] = await Promise.all([getHealth(), getHealthDetail(), getRedisSummary(), getRedisInfo(), getKnowledgeStats()])
    health.value=basic; healthDetail.value=detail; redisSummary.value=redis; redisInfo.value=info; knowledgeStats.value=knowledge
  } catch {}
}
async function handleRebuildKnowledge() {
  rebuilding.value=true
  try { await rebuildKnowledge(true); ElMessage.success('知识库重建完成'); await loadSystem() } catch {} finally { rebuilding.value=false }
}
async function handleKnowledgeSearch() {
  const query=knowledgeQuery.value.trim(); if(!query){ElMessage.warning('请输入检索内容');return}
  try { knowledgeResults.value=(await searchKnowledge(query, 5)).results || [] } catch {}
}
function openScene(row) {
  Object.assign(sceneForm, row ? { ...row, classNamesText: row.class_names.join(','), classNamesCnText: JSON.stringify(row.class_names_cn || {}, null, 2) } : { id: null, name: '', display_name: '', category: 'industry', classNamesText: '', classNamesCnText: '{}', description: '', is_active: true })
  sceneDialog.value = true
}
async function saveScene() {
  let cn
  try { cn = JSON.parse(sceneForm.classNamesCnText || '{}') } catch { ElMessage.error('中文映射必须是合法 JSON'); return }
  const data = { display_name: sceneForm.display_name, category: sceneForm.category, description: sceneForm.description, is_active: sceneForm.is_active, class_names: sceneForm.classNamesText.split(',').map((v) => v.trim()).filter(Boolean), class_names_cn: cn }
  if (sceneForm.id) await updateScene(sceneForm.id, data)
  else await createScene({ name: sceneForm.name, ...data })
  ElMessage.success('场景已保存'); sceneDialog.value = false; await loadAll()
}
async function removeScene(row) { await ElMessageBox.confirm(`删除场景 ${row.display_name}？`, '确认', { type: 'warning' }); await deleteScene(row.id); ElMessage.success('场景已删除'); await loadAll() }
onMounted(() => { loadAll(); loadSystem() })
</script>

<style scoped>.page-header,.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.page-header h2{margin:0}.toolbar{justify-content:flex-start;gap:8px}</style>
