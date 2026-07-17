<template>
  <div class="history-page">
    <!-- ── 页面标题 ── -->
    <div class="page-header">
      <div class="page-title-copy">
        <h2>历史记录</h2>
        <p>查询、筛选和查看过去的检测任务</p>
      </div>
      <h2>历史记录</h2>
      <el-button text @click="fetchList">
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <!-- ── 筛选栏 ── -->
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="类型">
          <el-select v-model="filters.task_type" placeholder="全部类型" clearable style="width: 130px">
            <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 130px">
            <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="场景">
          <el-select v-model="filters.scene_id" placeholder="全部场景" clearable style="width: 160px">
            <el-option
              v-for="scene in scenes"
              :key="scene.id"
              :label="scene.display_name"
              :value="scene.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="日期范围">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 260px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ── 任务列表 ── -->
    <el-card shadow="never" class="table-card">
      <el-table :data="tableData" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ typeText(row.task_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)">
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="场景" width="140">
          <template #default="{ row }">
            {{ row.scene_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="图片数" width="90">
          <template #default="{ row }">
            {{ row.total_images || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="目标数" width="90">
          <template #default="{ row }">
            {{ row.total_objects || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="推理耗时" width="110">
          <template #default="{ row }">
            {{ row.total_inference_time ? `${row.total_inference_time}ms` : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="viewDetail(row)">
              <el-icon><View /></el-icon>详情
            </el-button>
            <el-button
              v-if="row.status !== 'processing'"
              size="small"
              type="danger"
              text
              @click="handleDelete(row)"
            >
              <el-icon><Delete /></el-icon>删除
            </el-button>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty description="暂无检测记录" />
        </template>
      </el-table>

      <!-- ── 分页 ── -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[10, 20, 50]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchList"
          @current-change="fetchList"
        />
      </div>
    </el-card>

    <!-- ── 详情抽屉 ── -->
    <el-drawer v-model="drawerVisible" :title="`任务详情 #${detail.task?.id ?? ''}`" size="45%">
      <div v-loading="detailLoading">
        <el-descriptions :column="2" border v-if="detail.task">
          <el-descriptions-item label="类型">{{ typeText(detail.task.task_type) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="statusTagType(detail.task.status)">
              {{ statusText(detail.task.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="场景">{{ detail.task.scene_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="图片数">{{ detail.task.total_images || 0 }}</el-descriptions-item>
          <el-descriptions-item label="目标数">{{ detail.task.total_objects || 0 }}</el-descriptions-item>
          <el-descriptions-item label="推理耗时">
            {{ detail.task.total_inference_time ? `${detail.task.total_inference_time}ms` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="置信度阈值">{{ detail.task.conf_threshold ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="IOU 阈值">{{ detail.task.iou_threshold ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(detail.task.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ formatDate(detail.task.completed_at) }}</el-descriptions-item>
          <el-descriptions-item label="错误信息" :span="2" v-if="detail.task.error_message">
            <span class="error-text">{{ detail.task.error_message }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 类别分布 -->
        <div class="class-counts" v-if="detail.class_counts && Object.keys(detail.class_counts).length">
          <h4>类别分布</h4>
          <el-tag
            v-for="(count, name) in detail.class_counts"
            :key="name"
            class="class-tag"
            type="success"
          >
            {{ name }} × {{ count }}
          </el-tag>
        </div>

        <!-- 检测结果列表 -->
        <div class="result-list" v-if="detail.results && detail.results.length">
          <h4>检测结果列表</h4>
          <el-table :data="detail.results" size="small" stripe max-height="360">
            <el-table-column label="类别" min-width="100">
              <template #default="{ row }">{{ row.class_name_cn || row.class_name }}</template>
            </el-table-column>
            <el-table-column label="置信度" width="90">
              <template #default="{ row }">{{ row.confidence }}</template>
            </el-table-column>
            <el-table-column label="边界框" min-width="160">
              <template #default="{ row }">
                {{ Array.isArray(row.bbox) ? row.bbox.map((n) => Math.round(n)).join(', ') : '-' }}
              </template>
            </el-table-column>
            <el-table-column label="耗时" width="80">
              <template #default="{ row }">{{ row.inference_time ? `${row.inference_time}ms` : '-' }}</template>
            </el-table-column>
          </el-table>
        </div>

        <el-empty
          v-if="!detailLoading && detail.task && (!detail.results || !detail.results.length)"
          description="暂无检测结果"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
/**
 * HistoryPage.vue — 检测历史记录
 *
 * 功能：
 *   - 分页列表：类型/状态/场景/日期筛选
 *   - 详情抽屉：任务信息 + 类别分布 + 检测结果列表
 *   - 删除任务（二次确认）
 */
import { deleteTask, getScenes, getTaskDetail, getTaskList } from '@/api/history'
import { Delete, Refresh, RefreshLeft, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

// ── 类型/状态映射（与后端保持一致） ──
const typeOptions = [
  { label: '单图检测', value: 'single' },
  { label: '批量检测', value: 'batch' },
  { label: 'ZIP检测', value: 'zip' },
  { label: '视频检测', value: 'video' },
  { label: '摄像头检测', value: 'camera' },
]

const statusOptions = [
  { label: '已完成', value: 'completed' },
  { label: '处理中', value: 'processing' },
  { label: '失败', value: 'failed' },
  { label: '等待中', value: 'pending' },
]

const statusTagMap = {
  completed: 'success',
  processing: 'warning',
  failed: 'danger',
  pending: 'info',
}

function typeText(value) {
  return typeOptions.find((item) => item.value === value)?.label || value || '-'
}

function statusText(value) {
  return statusOptions.find((item) => item.value === value)?.label || value || '-'
}

function statusTagType(value) {
  return statusTagMap[value] || 'info'
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

// ── 筛选条件 ──
const filters = reactive({
  task_type: '',
  status: '',
  scene_id: '',
})
const dateRange = ref([])
const scenes = ref([])

// ── 列表数据 ──
const tableData = ref([])
const loading = ref(false)
const pagination = reactive({
  page: 1,
  page_size: 10,
  total: 0,
})

// ── 获取场景列表（用于筛选下拉框） ──
async function fetchScenes() {
  try {
    const res = await getScenes()
    scenes.value = res.scenes || []
  } catch (err) {
    console.error('[获取场景列表失败]', err)
  }
}

// ── 获取任务列表 ──
async function fetchList() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size,
      task_type: filters.task_type || undefined,
      status: filters.status || undefined,
      scene_id: filters.scene_id || undefined,
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined,
    }
    const res = await getTaskList(params)
    tableData.value = res.items || []
    pagination.total = res.total || 0
  } catch (err) {
    console.error('[获取历史记录失败]', err)
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  fetchList()
}

function handleReset() {
  filters.task_type = ''
  filters.status = ''
  filters.scene_id = ''
  dateRange.value = []
  pagination.page = 1
  fetchList()
}

// ── 详情抽屉 ──
const drawerVisible = ref(false)
const detailLoading = ref(false)
const detail = ref({ task: null, class_counts: {}, results: [] })

async function viewDetail(row) {
  drawerVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getTaskDetail(row.id)
  } catch (err) {
    console.error('[获取任务详情失败]', err)
  } finally {
    detailLoading.value = false
  }
}

// ── 删除任务 ──
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定要删除任务 #${row.id} 吗？此操作不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await deleteTask(row.id)
    ElMessage.success('删除成功')
    fetchList()
  } catch (err) {
    console.error('[删除任务失败]', err)
  }
}

onMounted(() => {
  fetchScenes()
  fetchList()
})
</script>

<style lang="scss" scoped>
.history-page {
  padding: 0;
  color: $text-regular;
  max-width: $page-max-width;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $spacing-lg;
  margin-bottom: $spacing-lg;

  > h2 {
    display: none;
  }
}

.page-title-copy h2 {
  margin: 0;
  color: $text-primary;
  font-size: 26px;
  font-weight: 650;
}

.page-title-copy p {
  margin: 6px 0 0;
  color: $text-secondary;
  font-size: 14px;
}

.filter-card {
  margin-bottom: 16px;
  border-radius: $border-radius-lg;
  background: rgba(24, 29, 36, 0.62);

  .filter-form {
    display: flex;
    flex-wrap: wrap;
    gap: $spacing-sm;

    :deep(.el-form-item) {
      margin-bottom: 0;
    }
  }
}

.table-card {
  border-radius: $border-radius-lg;
  background: rgba(24, 29, 36, 0.72);

  :deep(.el-table) {
    --el-table-header-bg-color: transparent;
    --el-table-tr-bg-color: transparent;
    --el-table-row-hover-bg-color: rgba(139, 92, 246, 0.08);
  }

  :deep(.el-table__empty-block) {
    min-height: 180px;
  }
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.class-counts {
  margin-top: 20px;

  h4 {
    margin: 0 0 10px;
    font-size: 14px;
    color: $text-primary;
  }

  .class-tag {
    margin: 0 8px 8px 0;
  }
}

.result-list {
  margin-top: 20px;

  h4 {
    margin: 0 0 10px;
    font-size: 14px;
    color: $text-primary;
  }
}

.error-text {
  color: #fca5a5;
}

@media (max-width: 760px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
