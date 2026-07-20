<template>
  <el-card class="task-list-card" shadow="never">
    <template #header>
      <div class="card-header">
        <span>训练任务列表</span>
        <el-button text :loading="loading" @click="$emit('refresh')">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </template>

    <AsyncState
      v-if="state !== 'success'"
      :state="state"
      :message="error"
      empty-text="暂无训练任务，点击右上角新建"
      compact
      @retry="$emit('refresh')"
    />

    <el-table v-else :data="tasks" stripe>
      <el-table-column label="任务 ID" width="110">
        <template #default="{ row }">{{ row.task_uuid?.slice(0, 8) }}</template>
      </el-table-column>
      <el-table-column prop="model_name" label="模型" width="115" />
      <el-table-column label="场景" min-width="135">
        <template #default="{ row }">{{ sceneName(row.scene_id) }}</template>
      </el-table-column>
      <el-table-column prop="device" label="设备" width="80" />
      <el-table-column label="进度" width="180">
        <template #default="{ row }">
          <el-progress
            :percentage="row.progress || 0"
            :status="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'exception' : ''"
            :stroke-width="14"
          />
        </template>
      </el-table-column>
      <el-table-column label="Epoch" width="100">
        <template #default="{ row }">{{ row.current_epoch }}/{{ row.epochs }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><StatusTag group="training" :status="row.status" /></template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="180" />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="$emit('select', row)">监控</el-button>
          <el-button
            v-if="['pending', 'running'].includes(row.status)"
            link
            type="danger"
            @click="$emit('stop', row)"
          >停止</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { Refresh } from '@element-plus/icons-vue'
import AsyncState from '@/components/common/AsyncState.vue'
import StatusTag from '@/components/common/StatusTag.vue'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  scenes: { type: Array, default: () => [] },
  loading: Boolean,
  state: { type: String, default: 'empty' },
  error: { type: String, default: '' },
})

defineEmits(['refresh', 'select', 'stop'])

const sceneName = (id) => props.scenes.find((scene) => scene.id === id)?.display_name || `场景 #${id ?? '-'}`
</script>

<style lang="scss" scoped>
.task-list-card {
  border-radius: $border-radius-lg;
  border-color: $border-color;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: $text-primary;
  font-weight: 650;
}
</style>
