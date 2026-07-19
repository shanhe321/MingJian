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
  Files,
  FolderOpened,
  Folder,
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
    label: '批量图片',
    description: '一次上传多张 PCB 图片',
    icon: Files,
  },
  {
    value: 'zip',
    label: 'ZIP 检测',
    description: '上传一个 ZIP 压缩包异步检测',
    icon: Folder,
  },
  {
    value: 'folder',
    label: '文件夹检测',
    description: '选择图片文件夹并异步检测',
    icon: FolderOpened,
  },
  {
    value: 'video',
    label: '视频检测',
    description: '上传视频并分析采样帧',
    icon: VideoCamera,
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
  border: 1px solid rgba(207, 216, 230, 0.92);
  border-radius: 999px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(239, 244, 252, 0.72));
  color: $text-regular;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.92);
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
    background:
      linear-gradient(135deg, rgba(91, 124, 250, 0.08), rgba(139, 92, 246, 0.06)),
      #fff;
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
  background:
    linear-gradient(135deg, rgba(91, 124, 250, 0.12), rgba(139, 92, 246, 0.1));
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
  background: rgba(91, 124, 250, 0.1);
}
</style>
