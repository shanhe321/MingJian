<template>
  <el-card shadow="never" class="settings-card">
    <template #header>
      <div class="card-header">
        <div>
          <strong>系统运行与知识库</strong>
          <small>查看依赖服务状态并执行受审计的知识库维护</small>
        </div>
        <el-button :loading="loading" @click="load">刷新状态</el-button>
      </div>
    </template>

    <AsyncState
      v-if="loadState !== 'success'"
      :state="loadState"
      :message="loadError"
      compact
      @retry="load"
    />
    <template v-else>
      <div class="health-grid">
        <article v-for="service in services" :key="service.name">
          <span class="health-dot" :class="service.status"></span>
          <div><strong>{{ service.name }}</strong><small>{{ service.message }}</small></div>
        </article>
      </div>
      <el-descriptions :column="2" border class="system-meta">
        <el-descriptions-item label="应用状态">{{ health?.data?.status || '-' }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ health?.data?.version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Redis Key 数">{{ redisSummary?.data?.key_count ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="Redis 模式">{{ redisInfo?.data?.use_redis === false ? '内存降级' : 'Redis' }}</el-descriptions-item>
        <el-descriptions-item label="知识片段">{{ knowledgeStats?.total_chunks ?? knowledgeStats?.count ?? 0 }}</el-descriptions-item>
      </el-descriptions>
    </template>

    <div class="knowledge-toolbar">
      <el-button type="warning" :loading="rebuilding" @click="rebuild">重建知识库</el-button>
      <el-input v-model="query" placeholder="输入 PCB 缺陷问题测试检索" @keyup.enter="search">
        <template #append><el-button :loading="searching" @click="search">检索</el-button></template>
      </el-input>
    </div>

    <AsyncState
      v-if="searchState && searchState !== 'success'"
      :state="searchState"
      :message="searchError"
      empty-text="未找到相关知识片段"
      compact
      @retry="search"
    />
    <el-table v-else-if="searchState === 'success'" :data="results" size="small">
      <el-table-column prop="source" label="来源" width="180" />
      <el-table-column prop="content" label="匹配内容" min-width="360" show-overflow-tooltip />
      <el-table-column prop="score" label="相似度" width="100" />
    </el-table>
  </el-card>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getHealth, getHealthDetail, getKnowledgeStats, getRedisInfo, getRedisSummary, rebuildKnowledge, searchKnowledge } from '@/api/system'
import AsyncState from '@/components/common/AsyncState.vue'
import { getErrorMessage } from '@/utils/errorMessages'

const health = ref(null)
const healthDetail = ref(null)
const redisSummary = ref(null)
const redisInfo = ref(null)
const knowledgeStats = ref(null)
const loading = ref(false)
const loadState = ref('loading')
const loadError = ref('')
const rebuilding = ref(false)
const searching = ref(false)
const searchState = ref('')
const searchError = ref('')
const query = ref('')
const results = ref([])

const services = computed(() => Object.entries(healthDetail.value?.data?.services || {}).map(([key, value]) => ({
  name: { database: 'PostgreSQL', redis: 'Redis', minio: 'MinIO' }[key] || key,
  status: value.status,
  message: value.message,
})))

async function load() {
  loading.value = true
  loadState.value = 'loading'
  loadError.value = ''
  try {
    const [basic, detail, redis, info, knowledge] = await Promise.all([
      getHealth(), getHealthDetail(), getRedisSummary(), getRedisInfo(), getKnowledgeStats(),
    ])
    health.value = basic
    healthDetail.value = detail
    redisSummary.value = redis
    redisInfo.value = info
    knowledgeStats.value = knowledge
    loadState.value = 'success'
  } catch (error) {
    loadState.value = 'error'
    loadError.value = getErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function rebuild() {
  try {
    await ElMessageBox.confirm('确认强制重建知识库索引？该操作可能需要较长时间。', '重建知识库', { type: 'warning' })
    rebuilding.value = true
    await rebuildKnowledge(true)
    ElMessage.success('知识库重建完成')
    await load()
  } catch {
    // 用户取消时不提示；接口错误由统一请求拦截器显示。
  } finally {
    rebuilding.value = false
  }
}

async function search() {
  const text = query.value.trim()
  if (!text) return ElMessage.warning('请输入检索内容')
  searching.value = true
  searchState.value = 'loading'
  searchError.value = ''
  try {
    results.value = (await searchKnowledge(text, 5)).results || []
    searchState.value = results.value.length ? 'success' : 'empty'
  } catch (error) {
    searchState.value = 'error'
    searchError.value = getErrorMessage(error)
  } finally {
    searching.value = false
  }
}

onMounted(load)
</script>

<style lang="scss" scoped>
.settings-card { border-radius: $border-radius-lg; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-header strong, .card-header small { display: block; }
.card-header small { margin-top: 4px; color: $text-secondary; font-weight: 400; }
.health-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.health-grid article { display: flex; align-items: center; gap: 10px; padding: 12px; border: 1px solid $border-color; border-radius: $border-radius-md; background: $surface-color-soft; }
.health-grid strong, .health-grid small { display: block; }
.health-grid small { margin-top: 3px; color: $text-secondary; font-size: 11px; }
.health-dot { width: 9px; height: 9px; border-radius: 50%; background: $text-placeholder; }
.health-dot.healthy { background: $success-color; }
.health-dot.unhealthy { background: $danger-color; }
.system-meta { margin-top: $spacing-md; }
.knowledge-toolbar { display: flex; gap: 10px; margin: 16px 0; }
.knowledge-toolbar .el-input { flex: 1; }
@media (max-width: 700px) {
  .health-grid { grid-template-columns: 1fr; }
  .knowledge-toolbar { flex-direction: column; }
}
</style>
