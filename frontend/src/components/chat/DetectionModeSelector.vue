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
  background: #fff;
  color: $text-regular;
  box-shadow: none;
  cursor: pointer;
  min-width: 122px;
  justify-content: flex-start;
  padding: 0 10px;
  white-space: nowrap;
  transition:
    background 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease;

  &:hover,
  &:focus-visible {
    border-color: $border-color-strong;
    background: #eef7ff;
    color: $text-primary;
    outline: none;
  }

  .chevron {
    margin-left: auto;
    color: $text-placeholder;
    font-size: 13px;
  }
}

.mode-menu {
  min-width: 284px;
}

.mode-option {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  gap: 11px;
}

.mode-option-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: #eaf4ff;
  color: $primary-color-light;
  flex-shrink: 0;
}

.mode-option-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  justify-content: center;

  strong {
    color: $text-primary;
    font-weight: 600;
    line-height: 1.25;
  }

  small {
    color: $text-secondary;
    font-size: 12px;
    line-height: 1.4;
  }
}

:global(.detection-mode-popper.el-popper) {
  padding: 0;
  border-radius: 12px;
}

:global(.detection-mode-popper .el-dropdown-menu) {
  min-width: 284px;
  margin: 0;
  padding: 6px;
  border-radius: 11px;
}

:global(.detection-mode-popper .el-dropdown-menu__item) {
  min-height: 58px;
  margin: 2px 0;
  padding: 7px 10px;
  border-radius: 8px;
  line-height: normal;
  box-sizing: border-box;
}

:global(.detection-mode-popper .el-dropdown-menu__item.is-selected) {
  background: #eaf4ff;
}

@media (max-width: 560px) {
  .mode-trigger {
    min-width: 110px;
  }

  :global(.detection-mode-popper .el-dropdown-menu) {
    min-width: min(284px, calc(100vw - 24px));
  }
}
</style>
