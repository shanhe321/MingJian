<template>
  <div class="dashboard-page">
    <PageHeader title="数据看板" description="洞察检测任务、质量结果、目标类别与系统趋势。">
      <template #actions>
        <div class="dashboard-controls">
        <el-radio-group v-if="userStore.isSuperuser" v-model="scope" @change="loadAllData" style="margin-right: 12px">
          <el-radio-button value="personal">个人</el-radio-button>
          <el-radio-button value="global">全局</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="periodDays" size="default" @change="loadAllData">
          <el-radio-button :value="7">近 7 天</el-radio-button>
          <el-radio-button :value="30">近 30 天</el-radio-button>
          <el-radio-button :value="90">近 90 天</el-radio-button>
        </el-radio-group>
        </div>
      </template>
    </PageHeader>

    <!-- ── 数字统计卡片 ── -->
    <el-row :gutter="16" class="stat-cards" v-loading="loading">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-icon stat-icon-tasks">
            <el-icon :size="28" color="#5b7cfa"><Document /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total_detections }}</div>
            <div class="stat-label">累计检测任务</div>
            <div class="stat-growth">今日 {{ stats.today_detections }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-icon stat-icon-images">
            <el-icon :size="28" color="#48b8f7"><PictureFilled /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ formatNumber(stats.total_items) }}</div>
            <div class="stat-label">累计处理 PCB</div>
            <div class="stat-growth">今日 {{ stats.today_items }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-icon stat-icon-objects">
            <el-icon :size="28" color="#8b5cf6"><Aim /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ formatNumber(stats.defective_pcbs) }}</div>
            <div class="stat-label">缺陷 PCB</div>
            <div class="stat-growth">合格 {{ stats.qualified_pcbs }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-icon stat-icon-time">
            <el-icon :size="28" color="#d99018"><Timer /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.pass_rate }}<span class="unit">%</span></div>
            <div class="stat-label">合格率</div>
            <div class="stat-growth">平均置信度 {{ stats.average_confidence }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ── 图表区域 ── -->
    <div v-if="!hasDashboardData && !loading" class="dashboard-empty-note">
      当前时间范围内暂无统计数据，图表会在检测任务产生后自动展示。
    </div>

    <el-row :gutter="16" class="chart-row">
      <!-- 每日检测趋势（折线图） -->
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>
            <span>每日检测趋势</span>
          </template>
          <div ref="trendChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <!-- 类别分布（饼图） -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>
            <span>类别分布</span>
          </template>
          <div ref="classChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <!-- 场景分布（柱状图） -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>
            <span>场景分布</span>
          </template>
          <div ref="sceneChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <!-- 任务类型分布（环形图） -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>风险等级分布</span></template>
          <div ref="riskChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>任务类型分布</span></template>
          <div ref="typeChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header><span>最近检测记录</span></template>
      <el-table :data="stats.recent_records || []" size="small">
        <el-table-column prop="task_id" label="任务" width="80" />
        <el-table-column v-if="scope === 'global'" prop="user_id" label="用户 ID" />
        <el-table-column prop="task_type" label="类型" />
        <el-table-column label="状态"><template #default="{ row }"><StatusTag group="detection" :status="row.status" /></template></el-table-column>
        <el-table-column prop="quality_conclusion" label="质检结论" />
        <el-table-column label="风险"><template #default="{ row }"><StatusTag group="risk" :status="row.risk_level" /></template></el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
/**
 * DashboardPage.vue — 数据看板
 *
 * 功能：
 *   - 数字统计卡片（带环比增长率）
 *   - ECharts 折线图：每日检测趋势
 *   - ECharts 饼图：类别分布
 *   - ECharts 柱状图：场景分布
 *   - ECharts 环形图：任务类型分布
 */
import { getOverview, getTypeDistribution } from '@/api/dashboard'
import { useUserStore } from '@/stores/user'
import { Aim, Document, PictureFilled, Timer } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'

// ── 响应式状态 ──
const periodDays = ref(30)
const scope = ref('personal')
const userStore = useUserStore()
const loading = ref(false)
const stats = ref({
  total_detections: 0, total_items: 0, defective_pcbs: 0, qualified_pcbs: 0,
  today_detections: 0, today_items: 0, pass_rate: 0, average_confidence: 0,
  recent_records: [],
})

const hasDashboardData = computed(() => {
  return Boolean(
    stats.value.total_detections
    || stats.value.total_items
    || stats.value.defective_pcbs
    || stats.value.qualified_pcbs
  )
})

// ── 图表 DOM 引用 ──
const trendChartRef = ref(null)
const classChartRef = ref(null)
const sceneChartRef = ref(null)
const typeChartRef = ref(null)
const riskChartRef = ref(null)

// ── 图表实例（用于销毁） ──
let trendChart = null
let classChart = null
let sceneChart = null
let typeChart = null
let riskChart = null
const CHART_THEME = undefined

// ── 格式化函数 ──
function formatNumber(num) {
  if (!num) return '0'
  if (num >= 10000) return (num / 10000).toFixed(1) + 'w'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'k'
  return String(num)
}

function formatGrowth(value) {
  if (value === undefined || value === null) return ''
  if (value > 0) return `+${value}%`
  if (value < 0) return `${value}%`
  return '持平'
}

function growthClass(key, inverse = false) {
  const val = stats.value.growth?.[key]
  if (val === undefined || val === null || val === 0) return 'growth-flat'
  // inverse=true 时，下降是好事（推理耗时越短越好）
  if (inverse) return val < 0 ? 'growth-up' : 'growth-down'
  return val > 0 ? 'growth-up' : 'growth-down'
}

// ── 加载所有数据 ──
async function loadAllData() {
  const days = periodDays.value
  loading.value = true
  try {
    const [overview, types] = await Promise.all([
      getOverview(days, scope.value),
      getTypeDistribution(days, scope.value),
    ])

    stats.value = overview
    renderTrendChart(overview.trend)
    renderClassChart(overview.class_distribution)
    renderSceneChart(overview.scene_distribution)
    renderRiskChart(overview.risk_distribution)
    renderTypeChart(types.distribution || [])
  } catch (err) {
    console.error('[看板数据加载失败]', err)
  } finally {
    loading.value = false
  }
}

// ── 渲染折线图：每日检测趋势 ──
function renderTrendChart(trend = []) {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value, CHART_THEME)
  }

  const dates = trend.map((d) => d.date.slice(5)) // "MM-DD"
  const taskCounts = trend.map((d) => d.task_count)
  const objectCounts = trend.map((d) => d.defect_count ?? d.object_count ?? 0)

  trendChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['检测任务', '检测目标'],
      bottom: 0,
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 40,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 11 },
    },
    yAxis: [
      {
        type: 'value',
        name: '任务数',
        axisLabel: { fontSize: 11 },
      },
      {
        type: 'value',
        name: '目标数',
        axisLabel: { fontSize: 11 },
      },
    ],
    series: [
      {
        name: '检测任务',
        type: 'line',
        data: taskCounts,
        smooth: true,
        lineStyle: { width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(91,124,250,0.22)' },
            { offset: 1, color: 'rgba(91,124,250,0.02)' },
          ]),
        },
        itemStyle: { color: '#5b7cfa' },
      },
      {
        name: '检测目标',
        type: 'line',
        yAxisIndex: 1,
        data: objectCounts,
        smooth: true,
        lineStyle: { width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(72,184,247,0.2)' },
            { offset: 1, color: 'rgba(72,184,247,0.02)' },
          ]),
        },
        itemStyle: { color: '#48b8f7' },
      },
    ],
  })
}

// ── 渲染饼图：类别分布 ──
function renderClassChart(distribution = []) {
  if (!classChartRef.value) return
  if (!classChart) {
    classChart = echarts.init(classChartRef.value, CHART_THEME)
  }

  classChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (params) => `${params.name}: ${params.value} (${params.percent}%)<br/>平均置信度: ${params.data.average_confidence ?? 0}`,
    },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: 10,
      top: 20,
      bottom: 20,
    },
    series: [
      {
        type: 'pie',
        radius: '65%',
        center: ['35%', '50%'],
        data: distribution,
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(15,23,42,0.12)',
          },
        },
        label: {
          formatter: '{b}\n{d}%',
          fontSize: 12,
        },
      },
    ],
  })
}

// ── 渲染柱状图：场景分布 ──
function renderSceneChart(distribution = []) {
  if (!sceneChartRef.value) return
  if (!sceneChart) {
    sceneChart = echarts.init(sceneChartRef.value, CHART_THEME)
  }

  sceneChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    grid: {
      left: 80,
      right: 20,
      top: 20,
      bottom: 30,
    },
    xAxis: {
      type: 'value',
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      data: distribution.map((d) => d.name),
      axisLabel: { fontSize: 12 },
    },
    series: [
      {
        type: 'bar',
        data: distribution.map((d) => d.value),
        barWidth: '50%',
        itemStyle: {
          borderRadius: [0, 4, 4, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#5b7cfa' },
            { offset: 1, color: '#48b8f7' },
          ]),
        },
        label: {
          show: true,
          position: 'right',
          fontSize: 12,
        },
      },
    ],
  })
}

// ── 渲染环形图：任务类型分布 ──
function renderRiskChart(distribution = []) {
  if (!riskChartRef.value) return
  if (!riskChart) riskChart = echarts.init(riskChartRef.value, CHART_THEME)
  const labels = { high: '高风险', medium: '中风险', low: '低风险', none: '无风险' }
  riskChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0 },
    color: ['#f56c6c', '#e6a23c', '#409eff', '#67c23a'],
    series: [{ type: 'pie', radius: ['40%', '65%'], center: ['50%', '45%'], data: distribution.map((item) => ({ ...item, name: labels[item.name] || item.name })), label: { formatter: '{b}\n{d}%' } }],
  })
}

function renderTypeChart(distribution = []) {
  if (!typeChartRef.value) return
  if (!typeChart) {
    typeChart = echarts.init(typeChartRef.value, CHART_THEME)
  }

  const colors = ['#5b7cfa', '#8b5cf6', '#48b8f7', '#16a368', '#d99018']

  typeChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)',
    },
    legend: {
      bottom: 0,
      itemGap: 16,
    },
    color: colors,
    series: [
      {
        type: 'pie',
        radius: ['40%', '65%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: false,
        data: distribution,
        label: {
          show: true,
          formatter: '{b}\n{d}%',
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold',
          },
        },
      },
    ],
  })
}

// ── 窗口 resize 时自动调整图表 ──
function handleResize() {
  trendChart?.resize()
  classChart?.resize()
  sceneChart?.resize()
  typeChart?.resize()
  riskChart?.resize()
}

onMounted(() => {
  loadAllData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  classChart?.dispose()
  sceneChart?.dispose()
  typeChart?.dispose()
  riskChart?.dispose()
})
</script>

<style lang="scss" scoped>
.dashboard-page {
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

/* 统计卡片 */
.stat-cards {
  margin-bottom: 16px;
}

.stat-card {
  border-radius: $border-radius-lg;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 251, 255, 0.86));
  border: 1px solid $border-color;
  box-shadow:
    $shadow-sm,
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease;

  &:hover {
    border-color: $border-color-strong;
    transform: translateY(-2px);
    box-shadow: $shadow-md;
  }

  :deep(.el-card__body) {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px;
  }
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid rgba(148, 163, 184, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.stat-icon-tasks {
  background: rgba(139, 92, 246, 0.14);
}

.stat-icon-images {
  background: rgba(72, 184, 247, 0.12);
}

.stat-icon-objects {
  background: rgba(139, 92, 246, 0.12);
}

.stat-icon-time {
  background: rgba(217, 144, 24, 0.12);
}

.stat-info {
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: 27px;
  font-weight: 700;
  color: $text-primary;
  line-height: 1.2;

  .unit {
    font-size: 14px;
    font-weight: 400;
    color: $text-secondary;
    margin-left: 2px;
  }
}

.stat-label {
  font-size: 13px;
  color: $text-secondary;
  margin-top: 2px;
}

.stat-growth {
  font-size: 12px;
  margin-top: 4px;

  &.growth-up {
    color: $success-color;
    &::before {
      content: '↑ ';
    }
  }

  &.growth-down {
    color: $danger-color;
    &::before {
      content: '↓ ';
    }
  }

  &.growth-flat {
    color: $text-placeholder;
  }
}

/* 图表区域 */
.chart-row {
  margin-bottom: 16px;

  :deep(.el-card) {
    border-radius: $border-radius-lg;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 251, 255, 0.88));
    border-color: $border-color;
    box-shadow:
      $shadow-sm,
      inset 0 1px 0 rgba(255, 255, 255, 0.95);
  }
}

.dashboard-empty-note {
  margin: 0 0 $spacing-md;
  padding: 12px 14px;
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  background: rgba(91, 124, 250, 0.06);
  color: $text-secondary;
  font-size: 13px;
}

.chart-container {
  height: 320px;
  width: 100%;
  border-radius: $border-radius-md;
  background:
    radial-gradient(circle at 80% 0, rgba(91, 124, 250, 0.06), transparent 36%),
    rgba(248, 250, 255, 0.88);
}

@media (max-width: 900px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
