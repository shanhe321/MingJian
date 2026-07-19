<template>
  <section class="control-panel">
    <header class="panel-heading">
      <div>
        <span class="eyebrow">CAMERA CONTROL</span>
        <h2>实时控制</h2>
      </div>
      <span class="status-pill" :class="statusClass">
        <i></i>{{ statusText }}
      </span>
    </header>

    <el-alert v-if="error" type="error" :closable="false" :title="error" show-icon />

    <div class="channel-status" aria-label="实时连接状态">
      <span :class="{ connected: cameraReady }"><i></i>摄像头 {{ cameraReady ? '已连接' : '未连接' }}</span>
      <span :class="{ connected: inferenceConnected }"><i></i>推理通道 {{ inferenceConnected ? '已连接' : '未连接' }}</span>
    </div>

    <el-form label-position="top" class="control-form">
      <el-form-item label="检测场景">
        <el-select
          :model-value="sceneId"
          placeholder="使用场景默认模型"
          :disabled="locked"
          @update:model-value="$emit('update:sceneId', $event)"
        >
          <el-option
            v-for="scene in scenes"
            :key="scene.id"
            :label="scene.display_name || scene.name"
            :value="scene.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="推理设备">
        <el-select
          :model-value="device"
          :disabled="locked"
          @update:model-value="$emit('update:device', $event)"
        >
          <el-option label="CPU · 兼容模式" value="cpu" />
          <el-option label="GPU · 高性能" value="gpu" />
        </el-select>
      </el-form-item>

      <el-form-item>
        <template #label>
          <span class="slider-label"><span>置信度</span><strong>{{ confidence.toFixed(2) }}</strong></span>
        </template>
        <el-slider
          :model-value="confidence"
          :min="0.1"
          :max="0.9"
          :step="0.05"
          :disabled="locked"
          @update:model-value="$emit('update:confidence', $event)"
        />
      </el-form-item>

      <el-form-item>
        <template #label>
          <span class="slider-label"><span>IOU 阈值</span><strong>{{ iou.toFixed(2) }}</strong></span>
        </template>
        <el-slider
          :model-value="iou"
          :min="0.1"
          :max="0.9"
          :step="0.05"
          :disabled="locked"
          @update:model-value="$emit('update:iou', $event)"
        />
      </el-form-item>
    </el-form>

    <button v-if="!running" type="button" class="primary-action" :disabled="connecting" @click="$emit('start')">
      <el-icon v-if="connecting" class="is-loading"><Loading /></el-icon>
      <el-icon v-else><VideoCamera /></el-icon>
      {{ connecting ? '正在连接摄像头' : '启动实时检测' }}
    </button>
    <button v-else type="button" class="stop-action" @click="$emit('stop')">
      <span></span>停止实时检测
    </button>

    <p class="permission-note">
      <el-icon><Lock /></el-icon>
      视频仅用于实时推理，浏览器会先请求摄像头权限。
    </p>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Loading, Lock, VideoCamera } from '@element-plus/icons-vue'

const props = defineProps({
  scenes: { type: Array, default: () => [] },
  sceneId: { type: Number, default: null },
  device: { type: String, default: 'cpu' },
  confidence: { type: Number, default: 0.25 },
  iou: { type: Number, default: 0.45 },
  running: Boolean,
  connecting: Boolean,
  error: { type: String, default: '' },
  cameraReady: Boolean,
  inferenceConnected: Boolean,
})

defineEmits([
  'update:sceneId',
  'update:device',
  'update:confidence',
  'update:iou',
  'start',
  'stop',
])

const locked = computed(() => props.running || props.connecting)
const statusText = computed(() => {
  if (props.error) return '异常'
  if (props.connecting) return '连接中'
  if (props.running) return '运行中'
  return '未启动'
})
const statusClass = computed(() => {
  if (props.error) return 'is-error'
  if (props.connecting) return 'is-connecting'
  if (props.running) return 'is-running'
  return 'is-idle'
})
</script>

<style lang="scss" scoped>
.control-panel {
  flex: 0 0 auto;
  padding: 13px 14px 10px;
  border-bottom: 1px solid rgba(207, 216, 230, 0.72);
  background: transparent;
  box-sizing: border-box;
}

.panel-heading,
.slider-label,
.status-pill,
.primary-action,
.stop-action,
.permission-note {
  display: flex;
  align-items: center;
}

.panel-heading {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 9px;
}

.eyebrow {
  color: $primary-color;
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.14em;
}

h2 {
  margin: 3px 0 0;
  color: $text-primary;
  font-size: 16px;
}

.status-pill {
  gap: 6px;
  height: 26px;
  padding: 0 9px;
  border-radius: 999px;
  background: #f1f4f9;
  color: $text-secondary;
  font-size: 10px;
  font-weight: 650;

  i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #94a3b8;
  }

  &.is-running {
    background: rgba(22, 163, 104, 0.09);
    color: $success-color;

    i {
      background: $success-color;
      box-shadow: 0 0 0 4px rgba(22, 163, 104, 0.1);
    }
  }

  &.is-connecting {
    background: rgba(245, 158, 11, 0.1);
    color: $warning-color;

    i { background: $warning-color; }
  }

  &.is-error {
    background: rgba(239, 68, 68, 0.09);
    color: $danger-color;

    i { background: $danger-color; }
  }
}

.control-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
  margin-top: 9px;

  :deep(.el-form-item) {
    min-width: 0;
    margin-bottom: 0;
  }

  :deep(.el-form-item__label) {
    width: 100%;
    color: $text-secondary;
    height: 20px;
    padding: 0;
    font-size: 10px;
    font-weight: 600;
  }

  :deep(.el-select) { width: 100%; }
  :deep(.el-select__wrapper) {
    min-height: 34px;
    border-radius: 10px;
    background: #f8faff;
    box-shadow: 0 0 0 1px rgba(207, 216, 230, 0.78) inset;
  }

  :deep(.el-slider__bar) {
    background: linear-gradient(90deg, $primary-color-light, #7765ed);
  }

  :deep(.el-slider__button) {
    width: 15px;
    height: 15px;
    border-color: $primary-color;
  }

  :deep(.el-slider) {
    height: 30px;
  }
}

.channel-status {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin: 7px 0 2px;

  span {
    display: flex;
    min-width: 0;
    height: 25px;
    align-items: center;
    gap: 5px;
    padding: 0 7px;
    overflow: hidden;
    border-radius: 8px;
    background: rgba(241, 244, 249, 0.82);
    color: $text-secondary;
    font-size: 9px;
    text-overflow: ellipsis;
    white-space: nowrap;

    i {
      width: 5px;
      height: 5px;
      flex: 0 0 5px;
      border-radius: 50%;
      background: #a8b2c2;
    }

    &.connected {
      background: rgba(22, 163, 104, 0.075);
      color: $success-color;

      i { background: $success-color; }
    }
  }
}

.slider-label {
  width: 100%;
  justify-content: space-between;

  strong {
    color: $primary-color-dark;
    font-size: 11px;
  }
}

.primary-action,
.stop-action {
  width: 100%;
  height: 44px;
  justify-content: center;
  gap: 8px;
  border-radius: 12px;
  cursor: pointer;
  font-weight: 650;
  margin-top: 11px;
}

.primary-action {
  border: 0;
  background: linear-gradient(135deg, $primary-color-light, #6f5ce7);
  color: #fff;
  box-shadow: 0 11px 24px rgba(91, 124, 250, 0.22);

  &:disabled { opacity: 0.7; cursor: wait; }
}

.stop-action {
  border: 1px solid rgba(239, 68, 68, 0.18);
  background: rgba(254, 242, 242, 0.8);
  color: $danger-color;

  span {
    width: 9px;
    height: 9px;
    border-radius: 2px;
    background: currentColor;
  }
}

.permission-note {
  align-items: flex-start;
  gap: 6px;
  margin: 6px 2px 0;
  color: $text-placeholder;
  font-size: 9px;
  line-height: 1.5;
}
</style>
