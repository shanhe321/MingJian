<template>
  <section class="chat-input-shell" aria-label="消息输入">
    <div v-if="selectedFiles.length" class="selected-file-panel">
      <div class="selected-file-main">
        <img v-if="previewUrl" :src="previewUrl" alt="已选图片预览" />
        <span v-else class="selected-file-icon">
          <el-icon><component :is="currentMode.icon" /></el-icon>
        </span>
        <span class="selected-file-copy">
          <strong>{{ fileTitle }}</strong>
          <small>{{ fileMeta }}</small>
          <small v-if="fileExtra">{{ fileExtra }}</small>
        </span>
      </div>
      <button type="button" class="remove-file" aria-label="移除已选文件" @click="$emit('clear-files')">
        <el-icon><Close /></el-icon>
      </button>
    </div>

    <div v-if="selectedFiles.length > 1" class="selected-file-list">
      <span v-for="file in selectedFiles.slice(0, 3)" :key="file.name">{{ file.name }}</span>
      <span v-if="selectedFiles.length > 3">还有 {{ selectedFiles.length - 3 }} 个</span>
    </div>

    <div class="composer">
      <el-input
        ref="textInput"
        :model-value="modelValue"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 5 }"
        resize="none"
        :placeholder="currentMode.placeholder"
        :disabled="loading"
        aria-label="向 RSOD Agent 发送消息"
        @update:model-value="$emit('update:modelValue', $event)"
        @keydown.enter.exact.prevent="$emit('send')"
      />

      <div class="composer-toolbar">
        <div class="composer-tools">
          <el-tooltip content="添加附件" placement="top">
            <button
              type="button"
              class="tool-button attachment-button"
              :disabled="loading"
              aria-label="添加附件"
              @click="fileInput?.click()"
            >
              <el-icon><Paperclip /></el-icon>
            </button>
          </el-tooltip>

          <DetectionModeSelector
            :model-value="modeValue"
            @update:model-value="$emit('update:modeValue', $event)"
          />

          <input
            ref="fileInput"
            type="file"
            :accept="currentMode.accept"
            :multiple="currentMode.multiple"
            :webkitdirectory="modeValue === 'folder' ? '' : null"
            :directory="modeValue === 'folder' ? '' : null"
            hidden
            @change="handleFileChange"
          />
        </div>

        <div class="composer-actions">
          <el-tooltip v-if="hasMessages && !loading" content="清空当前对话" placement="top">
            <button type="button" class="tool-button" aria-label="清空当前对话" @click="$emit('new-chat')">
              <el-icon><Delete /></el-icon>
            </button>
          </el-tooltip>

          <button v-if="!loading" type="button" class="send-button" :disabled="!canSend" aria-label="发送" @click="$emit('send')">
            <el-icon><ArrowUp /></el-icon>
          </button>
          <button v-else-if="stoppable" type="button" class="stop-button" aria-label="停止生成" @click="$emit('stop')">
            <span></span>
          </button>
          <button v-else type="button" class="loading-button" disabled aria-label="正在处理">
            <el-icon class="is-loading"><Loading /></el-icon>
          </button>
        </div>
      </div>
    </div>

    <p class="composer-hint">检测结果由模型生成，请结合实际情况复核。</p>
  </section>
</template>

<script setup>
import { nextTick, ref } from 'vue'
import { ArrowUp, Close, Delete, Loading, Paperclip } from '@element-plus/icons-vue'
import DetectionModeSelector from './DetectionModeSelector.vue'

defineProps({
  modelValue: { type: String, default: '' },
  modeValue: { type: String, default: 'single' },
  currentMode: { type: Object, required: true },
  selectedFiles: { type: Array, default: () => [] },
  previewUrl: { type: String, default: '' },
  fileTitle: { type: String, default: '' },
  fileMeta: { type: String, default: '' },
  fileExtra: { type: String, default: '' },
  loading: Boolean,
  stoppable: Boolean,
  canSend: Boolean,
  hasMessages: Boolean,
})

const emit = defineEmits([
  'update:modelValue',
  'update:modeValue',
  'file-select',
  'clear-files',
  'send',
  'stop',
  'new-chat',
])

const fileInput = ref(null)
const textInput = ref(null)

function focus() {
  nextTick(() => textInput.value?.focus())
}

defineExpose({ focus })

function handleFileChange(event) {
  emit('file-select', event)
  event.target.value = ''
}
</script>

<style lang="scss" scoped>
.chat-input-shell {
  width: min(960px, calc(100% - 24px));
  min-width: 0;
  flex: 0 0 auto;
  margin: 0 auto;
  box-sizing: border-box;
}

.composer {
  overflow: hidden;
  border: 1px solid rgba(181, 193, 214, 0.74);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.93);
  box-shadow:
    0 18px 46px rgba(46, 66, 108, 0.1),
    0 2px 8px rgba(46, 66, 108, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(20px) saturate(1.08);
  transition: border-color 0.18s ease, box-shadow 0.18s ease;

  &:focus-within {
    border-color: rgba(91, 124, 250, 0.42);
    box-shadow:
      0 20px 52px rgba(46, 66, 108, 0.12),
      0 0 0 3px rgba(91, 124, 250, 0.08);
  }

  :deep(.el-textarea__inner) {
    min-height: 54px !important;
    padding: 17px 20px 8px;
    border: 0;
    background: transparent;
    box-shadow: none;
    color: $text-primary;
    font-size: 15px;
    line-height: 1.55;

    &::placeholder {
      color: #96a0b3;
    }
  }
}

.composer-toolbar,
.composer-tools,
.composer-actions,
.selected-file-panel,
.selected-file-main {
  display: flex;
  align-items: center;
}

.composer-toolbar {
  justify-content: space-between;
  gap: 10px;
  padding: 4px 10px 10px 11px;
}

.composer-tools,
.composer-actions {
  gap: 6px;
}

.tool-button,
.send-button,
.stop-button,
.remove-file {
  display: inline-grid;
  place-items: center;
  border: 0;
  cursor: pointer;
}

.tool-button {
  width: 34px;
  height: 34px;
  border-radius: 11px;
  background: transparent;
  color: $text-secondary;

  &:hover:not(:disabled) {
    background: rgba(91, 124, 250, 0.08);
    color: $text-primary;
  }
}

.attachment-button {
  border: 1px solid rgba(207, 216, 230, 0.8);
  background: rgba(248, 250, 254, 0.86);
}

.send-button,
.stop-button {
  width: 36px;
  height: 36px;
  border-radius: 12px;
}

.loading-button {
  display: inline-grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 12px;
  background: #eef2f8;
  color: $primary-color;
}

.send-button {
  background: linear-gradient(135deg, $primary-color-light, #705cf3);
  color: #fff;
  box-shadow: 0 8px 18px rgba(91, 124, 250, 0.24);

  &:disabled {
    background: #d9dfeb;
    box-shadow: none;
    cursor: default;
  }
}

.stop-button {
  background: $text-primary;

  span {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    background: #fff;
  }
}

.selected-file-panel {
  justify-content: space-between;
  gap: 12px;
  width: min(430px, 100%);
  margin: 0 0 8px 10px;
  padding: 8px 9px;
  border: 1px solid rgba(91, 124, 250, 0.16);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 24px rgba(47, 68, 112, 0.06);
}

.selected-file-main {
  min-width: 0;
  gap: 9px;

  img,
  .selected-file-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    object-fit: cover;
  }

  .selected-file-icon {
    display: inline-grid;
    place-items: center;
    background: rgba(91, 124, 250, 0.09);
    color: $primary-color;
  }
}

.selected-file-copy {
  min-width: 0;

  strong,
  small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    color: $text-primary;
    font-size: 12px;
  }

  small {
    margin-top: 2px;
    color: $text-secondary;
    font-size: 10px;
  }
}

.remove-file {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  background: transparent;
  color: $text-placeholder;

  &:hover {
    background: rgba(239, 68, 68, 0.08);
    color: $danger-color;
  }
}

.selected-file-list {
  display: flex;
  gap: 5px;
  margin: 0 10px 7px;
  overflow: hidden;

  span {
    max-width: 180px;
    overflow: hidden;
    padding: 3px 7px;
    border-radius: 7px;
    background: rgba(91, 124, 250, 0.07);
    color: $text-secondary;
    font-size: 9px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.composer-hint {
  margin: 7px 0 0;
  color: $text-placeholder;
  font-size: 9px;
  text-align: center;
}

@media (max-width: 560px) {
  .chat-input-shell {
    width: calc(100% - 12px);
  }

  .composer {
    border-radius: 19px;
  }

  .composer-hint {
    display: none;
  }
}
</style>
