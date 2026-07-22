<template>
  <div class="training-page">
    <PageHeader title="模型训练">
      <template #actions>
        <el-button type="primary" @click="showCreateDialog = true">
          <el-icon><Plus /></el-icon>新建训练任务
        </el-button>
      </template>
    </PageHeader>

    <!-- ── 训练任务列表 ── -->
    <section v-if="tasksState === 'success' || tasksState === 'empty'" class="training-overview" aria-label="训练任务概览">
      <div v-for="item in taskOverviewCards" :key="item.label" class="overview-item">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </section>

    <TrainingTaskTable
      :tasks="taskList"
      :scenes="scenes"
      :loading="loadingTasks"
      :state="tasksState"
      :error="tasksError"
      @refresh="fetchTasks"
      @select="selectTask"
      @stop="stopTask"
    />

    <!-- ── 训练监控面板 ── -->
    <AsyncState
      v-if="selectedTask && statusState !== 'success'"
      :state="statusState"
      :message="statusError"
      compact
      @retry="fetchStatus"
    />
    <TrainingMonitor v-else :task="selectedTask" :metrics="metricCards">
      <template #loss-chart><div ref="lossChartRef" style="height:350px"></div></template>
      <template #map-chart><div ref="mapChartRef" style="height:350px"></div></template>
    </TrainingMonitor>

    <!-- ── 模型操作栏 ── -->
    <el-card
      v-if="selectedTask && selectedTask.status === 'completed'"
      class="action-card"
      shadow="never"
    >
      <template #header>
        <div class="card-header">
          <span>模型操作</span>
        </div>
      </template>

      <el-space wrap>
        <el-button
          type="primary"
          @click="validateModel"
          :loading="validating || selectedTask.is_evaluating || selectedTask.is_postprocessing"
          :disabled="selectedTask.is_evaluating || selectedTask.is_postprocessing"
        >
          评估模型
        </el-button>
        <el-button type="success" @click="showExportDialog = true">
          导出模型
        </el-button>
        <el-button @click="downloadModel">下载权重</el-button>
        <el-button @click="downloadResults">下载 results.csv</el-button>
        <el-button type="warning" @click="showPredictDialog = true">
          测试验证
        </el-button>
      </el-space>
      <el-alert
        v-if="selectedTask.is_postprocessing || selectedTask.is_evaluating"
        type="info"
        :closable="false"
        show-icon
        title="模型正在自动评估和整理产物，完成后可再次手动评估"
        style="margin-top: 12px"
      />
    </el-card>

    <!-- ── 评估报告面板 ── -->
    <EvaluationPanel :report="evalReport" :metrics="evalMetricCards" :per-class="perClassData" :weak-classes="weakClasses" />

    <!-- ── 新建训练任务对话框 ── -->
    <el-dialog
      v-model="showCreateDialog"
      title="新建训练任务"
      width="600px"
      :close-on-click-modal="false"
    >
      <AsyncState
        v-if="optionsState !== 'success'"
        :state="optionsState"
        :message="optionsError"
        empty-text="暂无可用的场景或数据集"
        compact
        @retry="fetchTrainingOptions"
      />

      <el-form v-else :model="trainForm" label-width="120px">
        <el-form-item label="检测场景">
          <el-select v-model="trainForm.scene_id" placeholder="选择场景" style="width: 100%">
            <el-option
              v-for="scene in scenes"
              :key="scene.id"
              :label="scene.display_name"
              :value="scene.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="训练数据集">
          <el-select
            v-model="trainForm.dataset_project_id"
            placeholder="选择已校验的数据集"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="dataset in availableDatasets"
              :key="dataset.id"
              :label="`${dataset.name}（${dataset.total_images} 张）`"
              :value="dataset.id"
            />
          </el-select>
          <div class="form-hint">仅显示当前场景下状态为 ready 的数据集；不选择时使用兼容目录。</div>
        </el-form-item>

        <el-form-item label="基础模型">
          <el-select v-model="trainForm.model_name">
            <el-option label="YOLOv11n (Nano, 最快)" value="yolov11n" />
            <el-option label="YOLOv11s (Small)" value="yolov11s" />
            <el-option label="YOLOv11m (Medium)" value="yolov11m" />
            <el-option label="YOLOv11l (Large)" value="yolov11l" />
            <el-option label="YOLOv11x (XLarge, 最强)" value="yolov11x" />
          </el-select>
        </el-form-item>

        <el-form-item label="训练轮数">
          <el-slider v-model="trainForm.epochs" :min="10" :max="500" :step="10" show-input />
        </el-form-item>

        <el-form-item label="批次大小">
          <el-input-number v-model="trainForm.batch_size" :min="1" :max="64" :step="2" />
        </el-form-item>

        <el-form-item label="图像尺寸">
          <el-select v-model="trainForm.img_size">
            <el-option label="416" :value="416" />
            <el-option label="512" :value="512" />
            <el-option label="640 (默认)" :value="640" />
            <el-option label="768" :value="768" />
          </el-select>
        </el-form-item>

        <el-form-item label="训练设备">
          <el-radio-group v-model="trainForm.device">
            <el-radio value="cpu">CPU (本地)</el-radio>
            <el-radio value="0">GPU:0</el-radio>
            <el-radio value="1">GPU:1</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="优化器">
          <el-select v-model="trainForm.optimizer">
            <el-option label="SGD (推荐)" value="SGD" />
            <el-option label="Adam" value="Adam" />
            <el-option label="AdamW" value="AdamW" />
          </el-select>
        </el-form-item>

        <el-form-item label="初始学习率">
          <el-input-number
            v-model="trainForm.lr0"
            :min="0.0001"
            :max="0.1"
            :step="0.001"
            :precision="4"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="optionsState !== 'success'"
          :loading="creating"
          @click="createTask"
        >
          启动训练
        </el-button>
      </template>
    </el-dialog>

    <!-- ── 导出模型对话框 ── -->
    <ModelExportDialog v-model="showExportDialog" :form="exportForm" :is-admin="userStore.isSuperuser" :loading="exporting" @submit="exportModel" />

    <!-- ── 测试图验证对话框 ── -->
    <el-dialog
      v-model="showPredictDialog"
      title="测试图验证"
      width="900px"
      @close="resetPredictState"
    >
      <el-row :gutter="16">
        <!-- 左侧：上传 + 配置 -->
        <el-col :span="10">
          <el-upload
            class="predict-upload"
            drag
            action=""
            :auto-upload="false"
            :on-change="handlePredictFileChange"
            accept="image/*"
            :limit="1"
          >
            <el-icon style="font-size: 40px; color: #909399"><UploadFilled /></el-icon>
            <div>拖拽图片到此处，或 <em>点击上传</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 JPG/PNG/BMP 格式，请使用不在训练集/验证集中的全新图片</div>
            </template>
          </el-upload>

          <el-form label-width="80px" style="margin-top: 16px">
            <el-form-item label="置信度">
              <el-slider v-model="predictConf" :min="0.05" :max="0.95" :step="0.05" show-input />
            </el-form-item>
            <el-form-item label="IoU">
              <el-slider v-model="predictIou" :min="0.1" :max="0.9" :step="0.05" show-input />
            </el-form-item>
          </el-form>

          <el-button
            type="primary"
            style="width: 100%; margin-top: 8px"
            @click="runPredict"
            :loading="predicting"
            :disabled="!predictFile"
          >
            开始检测
          </el-button>
        </el-col>

        <!-- 右侧：检测结果 -->
        <el-col :span="14">
          <div v-if="predictResult">
            <img
              :src="`data:image/jpeg;base64,${predictResult.annotated_image}`"
              style="width: 100%; border-radius: 8px; margin-bottom: 12px"
            />
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="检测目标数">
                {{ predictResult.total_objects }}
              </el-descriptions-item>
              <el-descriptions-item label="推理耗时">
                {{ predictResult.inference_time }}ms
              </el-descriptions-item>
            </el-descriptions>

            <el-table
              :data="predictResult.detections"
              stripe
              size="small"
              style="margin-top: 8px; max-height: 200px"
            >
              <el-table-column prop="class_name" label="类别" width="120" />
              <el-table-column label="置信度" width="100">
                <template #default="{ row }">
                  {{ (row.confidence * 100).toFixed(1) }}%
                </template>
              </el-table-column>
              <el-table-column label="位置">
                <template #default="{ row }">
                  [{{ row.bbox.map((v) => v.toFixed(0)).join(', ') }}]
                </template>
              </el-table-column>

              <template #empty>
                <el-empty description="未检测到目标" :image-size="60" />
              </template>
            </el-table>
          </div>
          <el-empty v-else description="上传图片并点击检测" />
        </el-col>
      </el-row>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, UploadFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getDatasets } from '@/api/datasets'
import { getScenes } from '@/api/scenes'
import {
  downloadTrainingResults,
  downloadTrainingWeights,
  evaluateTraining,
  exportTrainingModel,
  getTrainingMetrics,
  getTrainingStatus,
  getTrainingTasks,
  predictTrainingImage,
  startTraining,
  stopTraining,
} from '@/api/training'
import { useUserStore } from '@/stores/user'
import { statusLabel, statusType as resolveStatusType } from '@/utils/statusMaps'
import { buildTrainingExportPayload } from '@/utils/trainingExport'
import TrainingTaskTable from '@/components/training/TrainingTaskTable.vue'
import TrainingMonitor from '@/components/training/TrainingMonitor.vue'
import EvaluationPanel from '@/components/training/EvaluationPanel.vue'
import ModelExportDialog from '@/components/training/ModelExportDialog.vue'
import AsyncState from '@/components/common/AsyncState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { getErrorMessage } from '@/utils/errorMessages'

const userStore = useUserStore()

// ── 状态变量 ──
const taskList = ref([])
const loadingTasks = ref(false)
const tasksState = ref('loading')
const tasksError = ref('')
const selectedTask = ref(null)
const statusState = ref('success')
const statusError = ref('')
const datasets = ref([])
const scenes = ref([])
const optionsState = ref('loading')
const optionsError = ref('')
const showCreateDialog = ref(false)
const creating = ref(false)

// ── 模型评估相关状态 ──
const evalReport = ref(null)
const validating = ref(false)

// ── 模型导出相关状态 ──
const showExportDialog = ref(false)
const exporting = ref(false)
const exportForm = ref({
  version: '',
  description: '',
  set_default: false,
  upload_minio: true,
})

// ── 测试图验证相关状态 ──
const showPredictDialog = ref(false)
const predicting = ref(false)
const predictFile = ref(null)
const predictConf = ref(0.25)
const predictIou = ref(0.45)
const predictResult = ref(null)

// ── 图表引用 ──
const lossChartRef = ref(null)
const mapChartRef = ref(null)
let lossChart = null
let mapChart = null
const taskOverviewCards = computed(() => {
  const total = taskList.value.length
  const running = taskList.value.filter((task) => ['pending', 'running'].includes(task.status)).length
  const completed = taskList.value.filter((task) => task.status === 'completed').length
  return [
    { label: '全部任务', value: total },
    { label: '进行中', value: running },
    { label: '已完成', value: completed },
    { label: '当前任务', value: selectedTask.value?.task_uuid?.slice(0, 8) || '-' },
  ]
})
const CHART_THEME = undefined

// ── 当前任务的完整指标历史（用于图表 + 最新指标卡片）──
const taskMetrics = ref([])

// ── 轮询定时器 ──
let pollTimer = null

// ── 训练表单 ──
const defaultTrainForm = () => ({
  scene_id: null,
  dataset_project_id: null,
  model_name: 'yolov11n',
  epochs: 50,
  batch_size: 8,
  img_size: 640,
  device: 'cpu',
  optimizer: 'SGD',
  lr0: 0.01,
})
const trainForm = ref(defaultTrainForm())
const availableDatasets = computed(() => datasets.value.filter(
  (dataset) => dataset.status === 'ready' && dataset.scene_id === trainForm.value.scene_id,
))

watch(() => trainForm.value.scene_id, () => {
  if (!availableDatasets.value.some((dataset) => dataset.id === trainForm.value.dataset_project_id)) {
    trainForm.value.dataset_project_id = null
  }
})

async function fetchTrainingOptions() {
  optionsState.value = 'loading'
  optionsError.value = ''
  try {
    const [sceneRes, datasetRes] = await Promise.all([getScenes(), getDatasets()])
    scenes.value = sceneRes.items || []
    datasets.value = datasetRes.items || []
    optionsState.value = scenes.value.length ? 'success' : 'empty'
    if (!trainForm.value.scene_id && scenes.value.length) {
      trainForm.value.scene_id = scenes.value[0].id
    }
  } catch (error) {
    optionsState.value = 'error'
    optionsError.value = getErrorMessage(error)
  }
}

// ── 计算属性：最新指标卡片 ──
const metricCards = computed(() => {
  if (!selectedTask.value) return []
  const metrics = taskMetrics.value
  const m = metrics.length > 0 ? metrics[metrics.length - 1] : null
  if (!m) {
    return [
      { label: 'Epoch', value: `${selectedTask.value.current_epoch ?? 0}/${selectedTask.value.epochs ?? '-'}` },
      { label: '进度', value: `${selectedTask.value.progress ?? 0}%` },
      { label: 'Box Loss', value: '-' },
      { label: 'Cls Loss', value: '-' },
      { label: 'mAP@50', value: '-' },
      { label: 'mAP@50-95', value: '-' },
    ]
  }
  return [
    { label: 'Epoch', value: `${m.epoch}/${selectedTask.value.epochs ?? '-'}` },
    { label: 'Box Loss', value: m.box_loss != null ? m.box_loss.toFixed(4) : '-' },
    { label: 'Cls Loss', value: m.cls_loss != null ? m.cls_loss.toFixed(4) : '-' },
    { label: 'Precision', value: m.precision != null ? (m.precision * 100).toFixed(1) + '%' : '-' },
    { label: 'mAP@50', value: m.map50 != null ? (m.map50 * 100).toFixed(1) + '%' : '-' },
    { label: 'mAP@50-95', value: m.map50_95 != null ? (m.map50_95 * 100).toFixed(1) + '%' : '-' },
  ]
})

// ── 计算属性：评估报告整体指标卡片 ──
const evalMetricCards = computed(() => {
  if (!evalReport.value) return []
  const o = evalReport.value.overall || {}
  return [
    {
      label: 'Precision',
      value: o.precision != null ? (o.precision * 100).toFixed(1) + '%' : '-',
      color: o.precision > 0.7 ? '#16a368' : '#d99018',
    },
    {
      label: 'Recall',
      value: o.recall != null ? (o.recall * 100).toFixed(1) + '%' : '-',
      color: o.recall > 0.7 ? '#16a368' : '#d99018',
    },
    {
      label: 'mAP@50',
      value: o.map50 != null ? (o.map50 * 100).toFixed(1) + '%' : '-',
      color: o.map50 > 0.5 ? '#16a368' : '#dc5a5a',
    },
    {
      label: 'mAP@50-95',
      value: o.map50_95 != null ? (o.map50_95 * 100).toFixed(1) + '%' : '-',
      color: o.map50_95 > 0.3 ? '#16a368' : '#dc5a5a',
    },
  ]
})

// ── 计算属性：每类 AP 表格数据（按 AP@50 降序）──
const perClassData = computed(() => {
  if (!evalReport.value || !evalReport.value.per_class) return []
  return Object.entries(evalReport.value.per_class)
    .map(([name, m]) => ({
      class_name: name,
      ap50: m.ap50,
      ap50_95: m.ap50_95,
    }))
    .sort((a, b) => b.ap50 - a.ap50)
})

// ── 计算属性：弱势类别（AP@50 < 0.5）──
const weakClasses = computed(() => perClassData.value.filter((c) => c.ap50 < 0.5).map((c) => c.class_name))

// ── 每类 AP 表格行样式 ──
function tableRowClassName({ row }) {
  return row.ap50 < 0.5 ? 'weak-row' : ''
}

// ── 状态映射 ──
function statusType(status) {
  return resolveStatusType('training', status)
}

function statusText(status) {
  return statusLabel('training', status)
}

// ── 获取任务列表 ──
async function fetchTasks() {
  loadingTasks.value = true
  tasksState.value = 'loading'
  tasksError.value = ''
  try {
    // 注意：request 拦截器已经把响应解包为 response.data，这里拿到的就是接口返回体本身
    // 后端 GET /api/training/tasks 返回 { total, items }
    const res = await getTrainingTasks()
    taskList.value = res?.items || []
    tasksState.value = taskList.value.length ? 'success' : 'empty'
  } catch (e) {
    tasksState.value = 'error'
    tasksError.value = getErrorMessage(e)
  } finally {
    loadingTasks.value = false
  }
}

async function stopTask(task) {
  try {
    await ElMessageBox.confirm(`停止训练任务 ${task.task_uuid?.slice(0, 8)}？`, '确认停止', { type: 'warning' })
    await stopTraining(task.id)
    ElMessage.success('停止请求已提交')
    await fetchTasks()
    if (selectedTask.value?.id === task.id) await fetchStatus()
  } catch {}
}

// ── 选择任务并开始监控 ──
async function selectTask(task) {
  disposeCharts()
  selectedTask.value = task
  evalReport.value = null
  taskMetrics.value = []
  statusState.value = 'loading'
  statusError.value = ''
  resetPredictState()
  await fetchStatus()
  startPolling()
}

// ── 初始化 ECharts 图表 ──
function disposeCharts() {
  if (lossChart) lossChart.dispose()
  if (mapChart) mapChart.dispose()
  lossChart = null
  mapChart = null
}

function initCharts() {
  disposeCharts()
  if (lossChartRef.value) {
    lossChart = echarts.init(lossChartRef.value, CHART_THEME)
  }
  if (mapChartRef.value) {
    mapChart = echarts.init(mapChartRef.value, CHART_THEME)
  }
}

// ── 获取训练状态与指标并更新图表 ──
// 后端 GET /api/training/status/{id} 返回 { task, latest_metric, is_running }
// 完整的每轮指标历史需另外调用 GET /api/training/metrics/{id}
async function fetchStatus() {
  if (!selectedTask.value) return
  const taskId = selectedTask.value.id
  try {
    const statusRes = await getTrainingStatus(taskId)
    if (statusRes?.task) {
      selectedTask.value = {
        ...selectedTask.value,
        ...statusRes.task,
        is_evaluating: Boolean(statusRes.is_evaluating),
        is_postprocessing: Boolean(statusRes.is_postprocessing),
      }
    }

    const metricsRes = await getTrainingMetrics(taskId)
    const metrics = metricsRes?.metrics || []
    taskMetrics.value = metrics

    // 任务已结束（完成/失败/取消）则停止轮询
    if (
      selectedTask.value
      && !['pending', 'running'].includes(selectedTask.value.status)
      && !selectedTask.value.is_evaluating
      && !selectedTask.value.is_postprocessing
    ) {
      stopPolling()
    }
    statusState.value = 'success'
    statusError.value = ''
    // success 状态会重新挂载 TrainingMonitor，等待图表容器进入 DOM 后再初始化。
    await nextTick()
    if (!lossChart || !mapChart) {
      initCharts()
    }
    updateCharts(metrics)
  } catch (e) {
    disposeCharts()
    statusState.value = 'error'
    statusError.value = getErrorMessage(e)
    stopPolling()
  }
}

// ── 更新图表 ──
function updateCharts(metrics) {
  const epochs = metrics.map((m) => m.epoch)

  // Loss 曲线
  if (lossChart) {
    lossChart.setOption({
      backgroundColor: 'transparent',
      title: { text: '训练损失曲线', left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { data: ['Box Loss', 'Cls Loss', 'DFL Loss'], bottom: 0 },
      grid: { left: '10%', right: '5%', top: '15%', bottom: '15%' },
      xAxis: { type: 'category', data: epochs, name: 'Epoch' },
      yAxis: { type: 'value', name: 'Loss' },
      series: [
        {
          name: 'Box Loss',
          type: 'line',
          data: metrics.map((m) => m.box_loss),
          smooth: true,
          lineStyle: { width: 2 },
        },
        {
          name: 'Cls Loss',
          type: 'line',
          data: metrics.map((m) => m.cls_loss),
          smooth: true,
          lineStyle: { width: 2 },
        },
        {
          name: 'DFL Loss',
          type: 'line',
          data: metrics.map((m) => m.dfl_loss),
          smooth: true,
          lineStyle: { width: 2 },
        },
      ],
    })
  }

  // mAP 曲线
  if (mapChart) {
    mapChart.setOption({
      backgroundColor: 'transparent',
      title: { text: '评估指标曲线', left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { data: ['mAP@50', 'mAP@50-95', 'Precision', 'Recall'], bottom: 0 },
      grid: { left: '10%', right: '5%', top: '15%', bottom: '15%' },
      xAxis: { type: 'category', data: epochs, name: 'Epoch' },
      yAxis: { type: 'value', name: '指标值', max: 1 },
      series: [
        {
          name: 'mAP@50',
          type: 'line',
          data: metrics.map((m) => m.map50),
          smooth: true,
        lineStyle: { width: 2, color: '#3b82f6' },
        itemStyle: { color: '#3b82f6' },
        },
        {
          name: 'mAP@50-95',
          type: 'line',
          data: metrics.map((m) => m.map50_95),
          smooth: true,
        lineStyle: { width: 2, color: '#38bdf8' },
        itemStyle: { color: '#38bdf8' },
        },
        {
          name: 'Precision',
          type: 'line',
          data: metrics.map((m) => m.precision),
          smooth: true,
        lineStyle: { width: 2, type: 'dashed', color: '#0ea5e9' },
        itemStyle: { color: '#0ea5e9' },
        },
        {
          name: 'Recall',
          type: 'line',
          data: metrics.map((m) => m.recall),
          smooth: true,
          lineStyle: { width: 2, type: 'dashed', color: '#d99018' },
          itemStyle: { color: '#d99018' },
        },
      ],
    })
  }
}

// ── 轮询监控 ──
function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    if (selectedTask.value) {
      fetchStatus()
    }
  }, 5000) // 每 5 秒轮询一次
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ── 创建训练任务 ──
// 后端 POST /api/training/start 返回 { id, task_uuid, status, model_name, epochs, message }
async function createTask() {
  if (!trainForm.value.scene_id) {
    ElMessage.warning('请先选择检测场景')
    return
  }
  creating.value = true
  try {
    const res = await startTraining(trainForm.value)
    ElMessage.success(res?.message || `训练任务已创建：${res?.task_uuid?.slice(0, 8) || ''}`)
    showCreateDialog.value = false
    const selectedSceneId = trainForm.value.scene_id
    trainForm.value = { ...defaultTrainForm(), scene_id: selectedSceneId }
    await fetchTasks()
    // 响应体字段较少，从最新任务列表中找到完整任务对象再选中监控
    if (res?.id) {
      const fullTask = taskList.value.find((t) => t.id === res.id) || res
      selectTask(fullTask)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建训练任务失败')
  } finally {
    creating.value = false
  }
}

// ── 评估模型 ──
// 后端 POST /api/training/validate/{task_id} 会执行 model.val()，CPU 上耗时较长，超时调大到 5 分钟
async function validateModel() {
  if (!selectedTask.value) return
  if (selectedTask.value.is_evaluating || selectedTask.value.is_postprocessing) {
    ElMessage.info('模型正在自动评估，请等待当前任务完成')
    return
  }
  validating.value = true
  try {
    const taskId = selectedTask.value.id
    const res = await evaluateTraining(taskId, { split: 'val', conf: 0.001, iou: 0.6 })
    evalReport.value = res
    ElMessage.success(`评估完成: mAP50=${(res.overall.map50 * 100).toFixed(1)}%`)
  } catch (e) {
    // 响应拦截器已统一提示错误信息
  } finally {
    validating.value = false
  }
}

// ── 导出模型 ──
async function exportModel() {
  if (!selectedTask.value) return
  const normalizedVersion = exportForm.value.version.trim()
  if (normalizedVersion && !/^v?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/.test(normalizedVersion)) {
    ElMessage.warning('版本号应为 v1.0.0 或 1.0.0 格式')
    return
  }
  exporting.value = true
  try {
    const taskId = selectedTask.value.id
    const payload = buildTrainingExportPayload(exportForm.value, userStore.isSuperuser)
    const res = await exportTrainingModel(taskId, payload)
    ElMessage.success(res?.message || '模型导出成功')
    showExportDialog.value = false
  } catch (e) {
    // 响应拦截器已统一提示错误信息
  } finally {
    exporting.value = false
  }
}

// ── 下载模型权重 ──
async function downloadModel() {
  if (!selectedTask.value) return
  try {
    const taskId = selectedTask.value.id
    const blob = await downloadTrainingWeights(taskId)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `best_${selectedTask.value.task_uuid}.pt`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    ElMessage.success('模型下载已开始')
  } catch (e) {
    ElMessage.error('模型下载失败')
  }
}

async function downloadResults() {
  if (!selectedTask.value?.task_uuid) return
  try {
    const blob = await downloadTrainingResults(selectedTask.value.task_uuid)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `results_${selectedTask.value.task_uuid}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  } catch {}
}

// ── 测试图文件选择 ──
function handlePredictFileChange(file) {
  predictFile.value = file.raw
  predictResult.value = null
}

// ── 重置测试验证对话框状态 ──
function resetPredictState() {
  predictFile.value = null
  predictResult.value = null
}

// ── 运行测试图预测 ──
async function runPredict() {
  if (!predictFile.value || !selectedTask.value) return
  predicting.value = true
  try {
    const taskId = selectedTask.value.id
    const formData = new FormData()
    formData.append('file', predictFile.value)
    formData.append('task_id', taskId)
    formData.append('conf', predictConf.value)
    formData.append('iou', predictIou.value)

    // 不手动设置 Content-Type，交由浏览器自动生成 multipart boundary
    const res = await predictTrainingImage(formData)
    predictResult.value = res
    ElMessage.success(`检测完成: 发现 ${res.total_objects} 个目标`)
  } catch (e) {
    // 响应拦截器已统一提示错误信息
  } finally {
    predicting.value = false
  }
}

// ── 生命周期 ──
onMounted(() => {
  fetchTrainingOptions().catch((error) => console.error('获取训练选项失败', error))
  fetchTasks()
})

onBeforeUnmount(() => {
  stopPolling()
  disposeCharts()
})
</script>

<style lang="scss" scoped>
.training-page {
  padding: 0;
  color: $text-regular;
  max-width: $page-max-width;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: $spacing-lg;
  margin-bottom: $spacing-lg;
}

.page-header > h2 {
  display: none;
}

.page-title-copy h2 {
  margin: 0;
  font-size: 26px;
  color: $text-primary;
  font-weight: 650;
}

.page-title-copy p {
  margin: 6px 0 0;
  color: $text-secondary;
  font-size: 14px;
}

.training-overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: $spacing-sm;
  margin-bottom: $spacing-md;
}

.overview-item {
  min-height: 78px;
  padding: 14px 16px;
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  background: #fff;
  box-shadow:
    $shadow-sm,
    inset 0 1px 0 rgba(255, 255, 255, 0.96);

  span {
    display: block;
    color: $text-secondary;
    font-size: 12px;
  }

  strong {
    display: block;
    margin-top: 8px;
    color: $text-primary;
    font-size: 22px;
    font-weight: 700;
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.monitor-info {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: $text-secondary;
}

.metric-cards {
  margin-bottom: 8px;
}

.metric-item {
  text-align: center;
  padding: 8px 0;
  border-radius: $border-radius-md;
  background: $surface-color-soft;

  :deep(.el-card__body) {
    padding: 16px 12px;
  }
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  color: $text-primary;
}

.metric-label {
  font-size: 12px;
  color: $text-secondary;
  margin-top: 4px;
}

.task-list-card,
.monitor-card,
.action-card,
.eval-card {
  margin-bottom: 20px;
  border-radius: $border-radius-lg;
  background: #fff;
  border-color: $border-color;
  box-shadow:
    $shadow-sm,
    inset 0 1px 0 rgba(255, 255, 255, 0.95);
}

.task-list-card :deep(.el-table) {
  --el-table-header-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-row-hover-bg-color: #f4f9ff;
}

.task-list-card :deep(.el-table__empty-block) {
  min-height: 180px;
}

.predict-upload {
  width: 100%;
}

.form-hint {
  margin-top: 6px;
  color: $text-secondary;
  font-size: 12px;
  line-height: 1.5;
}

.predict-upload :deep(.el-upload-dragger) {
  width: 100%;
  padding: 20px;
  border-color: $border-color;
  background: $surface-color-soft;
  color: $text-secondary;

  &:hover {
    border-color: $border-color-strong;
    background: #fff;
  }
}

.weak-hint {
  margin-top: 16px;
  padding: 10px 12px;
  border: 1px solid rgba(220, 90, 90, 0.24);
  background-color: rgba(254, 242, 242, 0.9);
  color: $danger-color;
  border-radius: $border-radius-md;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

:deep(.weak-row) {
  background-color: rgba(254, 242, 242, 0.9) !important;
}

:deep(.weak-row td) {
  color: $danger-color !important;
}

@media (max-width: 900px) {
  .training-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .training-overview {
    grid-template-columns: 1fr;
  }
}
</style>
