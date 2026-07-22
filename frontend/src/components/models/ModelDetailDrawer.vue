<template>
  <el-drawer :model-value="modelValue" title="模型版本详情" size="min(720px, 92vw)" @update:model-value="$emit('update:modelValue', $event)">
    <AsyncState v-if="loading" state="loading" compact />
    <AsyncState v-else-if="error" state="error" :message="error" compact @retry="$emit('retry')" />
    <div v-else-if="model">
      <div class="model-heading">
        <div><span>{{ sceneName }}</span><h2>{{ model.version }} · {{ model.model_name }}</h2></div>
        <StatusTag group="model" :status="model.status" />
      </div>
      <ModelMetrics :model="model" />
      <el-descriptions :column="2" border class="details">
        <el-descriptions-item label="训练任务">#{{ model.training_task_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="默认模型">{{ model.is_default ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ model.model_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="文件大小">{{ model.file_size || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间" :span="2">{{ formatDate(model.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="说明" :span="2">{{ model.description || '-' }}</el-descriptions-item>
      </el-descriptions>
      <ModelArtifactPanel :artifacts="model.artifacts" :artifact-status="model.artifact_status" />
      <section class="per-class">
        <h3>各类别 AP</h3>
        <el-table :data="perClassRows" size="small">
          <el-table-column prop="displayName" label="类别">
            <template #default="{ row }">
              <span>{{ row.displayName }}</span>
              <small v-if="row.displayName !== row.className">{{ row.className }}</small>
            </template>
          </el-table-column>
          <el-table-column prop="value" label="AP"><template #default="{ row }">{{ formatMetricPercent(row.value) }}</template></el-table-column>
          <template #empty><el-empty description="暂无类别指标" :image-size="60" /></template>
        </el-table>
      </section>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'
import AsyncState from '@/components/common/AsyncState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ModelMetrics from './ModelMetrics.vue'
import ModelArtifactPanel from './ModelArtifactPanel.vue'
import { formatMetricPercent, normalizePerClassAp } from '@/utils/modelMetrics'

const props = defineProps({
  modelValue: Boolean,
  model: { type: Object, default: null },
  scenes: { type: Array, default: () => [] },
  loading: Boolean,
  error: { type: String, default: '' },
})
defineEmits(['update:modelValue', 'retry'])

const sceneName = computed(() => props.scenes.find((scene) => scene.id === props.model?.scene_id)?.display_name || `场景 #${props.model?.scene_id ?? '-'}`)
const perClassRows = computed(() => normalizePerClassAp(props.model?.per_class_ap))
const formatDate = (value) => value ? new Date(value).toLocaleString('zh-CN') : '-'
</script>

<style lang="scss" scoped>
.model-heading { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: $spacing-md; }
.model-heading span { color: $primary-color; font-size: 12px; }
.model-heading h2 { margin: 5px 0 0; color: $text-primary; font-size: 21px; }
.details, .per-class { margin-top: $spacing-lg; }
.per-class h3 { color: $text-primary; font-size: 15px; }
.per-class small { display: block; margin-top: 2px; color: $text-secondary; font-size: 11px; }
</style>
