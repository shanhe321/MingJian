<template>
  <el-dropdown
    trigger="click"
    placement="top-start"
    popper-class="rsod-dark-popper detection-mode-popper"
    @command="selectMode"
  >
    <button type="button" class="mode-trigger" :aria-label="`当前检测方式：${currentMode.label}`">
      <el-icon><component :is="currentMode.icon" /></el-icon>
      <span>{{ currentMode.label }}</span>
      <el-icon class="chevron"><ArrowDown /></el-icon>
    </button>

    <template #dropdown>
      <el-dropdown-menu class="mode-menu">
        <el-dropdown-item
          v-for="mode in modes"
          :key="mode.value"
          :command="mode.value"
          :class="{ 'is-selected': mode.value === modelValue }"
        >
          <div class="mode-option">
            <span class="mode-option-icon">
              <el-icon><component :is="mode.icon" /></el-icon>
            </span>
            <span class="mode-option-text">
              <strong>{{ mode.label }}</strong>
              <small>{{ mode.description }}</small>
            </span>
          </div>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import { computed } from 'vue'
import {
  ArrowDown,
  Camera,
  FolderOpened,
  Picture,
  VideoCamera,
} from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: 'single',
  },
})

const emit = defineEmits(['update:modelValue'])

const modes = [
  {
    value: 'single',
    label: '单图检测',
    description: '上传一张 PCB 图片并检测缺陷',
    icon: Picture,
  },
  {
    value: 'batch',
    label: '批量 / ZIP',
    description: '上传多张图片或 ZIP 压缩包',
    icon: FolderOpened,
  },
  {
    value: 'video',
    label: '视频检测',
    description: '上传视频并分析采样帧',
    icon: VideoCamera,
  },
  {
    value: 'camera',
    label: '摄像头',
    description: '进入实时摄像头检测工作台',
    icon: Camera,
  },
]

const currentMode = computed(() => {
  return modes.find((mode) => mode.value === props.modelValue) || modes[0]
})

function selectMode(mode) {
  emit('update:modelValue', mode)
}
</script>

<style lang="scss" scoped>
.mode-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 999px;
  background: rgba(35, 42, 53, 0.72);
  color: $text-regular;
  cursor: pointer;
  padding: 0 10px;
  white-space: nowrap;
  transition:
    background 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease;

  &:hover,
  &:focus-visible {
    border-color: $border-color-strong;
    background: $surface-color-elevated;
    color: $text-primary;
    outline: none;
  }

  .chevron {
    color: $text-placeholder;
    font-size: 13px;
  }
}

.mode-menu {
  min-width: 268px;
}

.mode-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 4px 0;
}

.mode-option-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  background: rgba(139, 92, 246, 0.12);
  color: $primary-color-light;
  flex-shrink: 0;
}

.mode-option-text {
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong {
    color: $text-primary;
    font-weight: 600;
  }

  small {
    color: $text-secondary;
    font-size: 12px;
    line-height: 1.4;
  }
}

:global(.detection-mode-popper .el-dropdown-menu__item.is-selected) {
  background: rgba(139, 92, 246, 0.12);
}
</style>
