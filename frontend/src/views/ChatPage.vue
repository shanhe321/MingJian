<template>
  <div class="chat-page" @dragover.prevent="handleDragOver" @dragleave.prevent="isDragging = false" @drop.prevent="handleDrop">
    <!-- ── 消息列表区域 ── -->
    <div class="message-list" ref="messageListRef">
      <div
        v-for="(msg, index) in agentStore.messages"
        :key="index"
        :class="['message-item', `message-${msg.role}`]"
      >
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="message-bubble user-bubble">
          <div class="message-content">{{ msg.content }}</div>
          <!-- 单张图片附件 -->
          <div v-if="msg.imagePreview" class="message-attachment">
            <img :src="msg.imagePreview" alt="附件图片" />
          </div>
          <!-- 多图附件（批量检测） -->
          <div v-if="msg.images && msg.images.length" class="message-attachments-grid">
            <img v-for="(src, i) in msg.images" :key="i" :src="src" alt="附件图片" />
          </div>
        </div>

        <!-- AI 消息 -->
        <div
          v-else-if="msg.role === 'assistant'"
          :class="['message-bubble', 'assistant-bubble', { 'is-error': msg.error }]"
        >
          <div v-if="msg.loading && !msg.content" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
          <div v-else class="message-content markdown-body" v-html="renderMarkdown(msg.content)"></div>

          <!-- 工具调用提示 -->
          <div v-if="msg.toolCall" class="tool-call-info">
            <el-tag size="small" type="info">🔧 调用工具：{{ msg.toolCall.tool }}</el-tag>
          </div>

          <!-- 检测结果卡片 -->
          <DetectionResultCard v-if="msg.detectionResult" :result="msg.detectionResult" />
        </div>
      </div>
    </div>

    <!-- ── 快捷操作栏 ── -->
    <div class="quick-actions">
      <el-button :disabled="agentStore.isLoading" @click="handleQuickDetect('single')">
        📷 单图检测
      </el-button>
      <el-button :disabled="agentStore.isLoading" @click="handleQuickDetect('batch')">
        📁 批量/ZIP
      </el-button>
      <el-button disabled>🎬 视频</el-button>
      <el-button disabled>📹 摄像头</el-button>
    </div>

    <!-- ── 输入区域 ── -->
    <div class="input-area">
      <!-- 已选文件预览 -->
      <div v-if="selectedFile" class="selected-file-chip">
        <span class="text-ellipsis">📎 {{ selectedFile.name }}</span>
        <el-icon class="remove-icon" @click="selectedFile = null"><Close /></el-icon>
      </div>

      <div class="input-row">
        <!-- 附件按钮 -->
        <el-button class="attach-btn" circle :disabled="agentStore.isLoading" @click="triggerFileInput">
          <el-icon><Paperclip /></el-icon>
        </el-button>
        <input
          ref="fileInputRef"
          type="file"
          accept="image/*,.zip"
          style="display: none"
          @change="handleFileSelect"
        />

        <!-- 文本输入框 -->
        <el-input
          v-model="inputText"
          placeholder="输入消息，或拖拽图片/ZIP 到这里..."
          :disabled="agentStore.isLoading"
          @keyup.enter="sendMessage"
        />

        <!-- 发送/停止按钮 -->
        <el-button v-if="!agentStore.isLoading" type="primary" :disabled="!canSend" @click="sendMessage">
          发送
        </el-button>
        <el-button v-else type="danger" @click="handleStop">停止</el-button>
      </div>
    </div>

    <!-- 拖拽遮罩 -->
    <div v-if="isDragging" class="drag-overlay">
      <div class="drag-overlay-content">
        <el-icon><UploadFilled /></el-icon>
        <p>释放以添加图片 / ZIP 附件</p>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * ChatPage.vue — 智能对话界面
 *
 * 功能：
 *   - 消息气泡（用户/AI 区分）
 *   - 文件附件上传（图片/ZIP 拖拽或选择）
 *   - SSE 流式渲染 AI 回复
 *   - 检测结果卡片展示
 *   - 快捷操作栏（单图/批量/视频/摄像头）
 *   - 中断当前对话
 */
import { detectBatch, detectSingle, detectZip } from '@/api/detection'
import DetectionResultCard from '@/components/DetectionResultCard.vue'
import { useAgentStore } from '@/stores/agent'
import { renderMarkdown } from '@/utils/markdown'
import request from '@/utils/request'
import { streamChat } from '@/utils/stream'
import { Close, Paperclip, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref } from 'vue'

// ── Store ──
const agentStore = useAgentStore()

// ── 响应式状态 ──
const inputText = ref('')
const selectedFile = ref(null)
const messageListRef = ref(null)
const fileInputRef = ref(null)
const isDragging = ref(false)

// ── 计算属性 ──
const canSend = computed(() => {
  return !agentStore.isLoading && (inputText.value.trim() || selectedFile.value)
})

/** 校验文件类型是否为图片或 ZIP */
function isValidAttachment(file) {
  return file.type.startsWith('image/') || file.name.toLowerCase().endsWith('.zip')
}

/** 滚动到底部 */
function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

/** 发送消息 */
async function sendMessage() {
  if (!canSend.value) return

  const message = inputText.value.trim()
  // ── 关键：在清空之前保存文件引用 ──
  const fileToSend = selectedFile.value
  const imagePreview = fileToSend && fileToSend.type.startsWith('image/')
    ? URL.createObjectURL(fileToSend)
    : null

  // 添加用户消息到列表
  agentStore.addMessage({
    role: 'user',
    content: message || (fileToSend ? `[附件] ${fileToSend.name}` : ''),
    image: fileToSend ? fileToSend.name : null,
    imagePreview,
  })

  // 清空输入
  inputText.value = ''
  selectedFile.value = null

  // 添加 AI 加载占位
  agentStore.addMessage({
    role: 'assistant',
    content: '',
    loading: true,
  })

  agentStore.setLoading(true)
  scrollToBottom()

  // ── 如果有附件图片，先上传到服务端获取真实路径 ──
  let serverImagePath = null
  if (fileToSend) {
    try {
      const formData = new FormData()
      formData.append('file', fileToSend)
      // 不设置 Content-Type，让 axios 自动添加 boundary
      const uploadResult = await request.post('/chat/upload', formData)
      serverImagePath = uploadResult.image_path
    } catch (err) {
      console.error('[图片上传失败]', err.response?.data || err.message || err)
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = `图片上传失败：${err.response?.data?.detail || err.message || '未知错误'}，请重试`
      lastMsg.loading = false
      lastMsg.error = true
      agentStore.setLoading(false)
      return
    }
  }

  // 发起 SSE 流式请求
  const requestBody = {
    message: message || '检测这张图片',
    ...(serverImagePath ? { image_path: serverImagePath } : {}),
  }

  let fullContent = ''

  const stop = streamChat('/api/chat/stream', requestBody, {
    onMessage: (data) => {
      if (data.type === 'text_chunk') {
        fullContent += data.content
        agentStore.updateLastAssistantMessage(fullContent)
        scrollToBottom()
      } else if (data.type === 'tool_call') {
        // 工具调用中，更新最后一条 AI 消息的工具信息
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.toolCall = { tool: data.tool, input: data.input }
      } else if (data.type === 'tool_result') {
        // 工具调用返回结果
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        try {
          const result = JSON.parse(data.result)
          if (result.detections) {
            // 有检测结果，设置到消息中
            lastMsg.detectionResult = result
            lastMsg.loading = false
          }
        } catch (e) {
          console.warn('[工具结果解析失败]', e.message)
          lastMsg.content += `\n[工具结果: ${data.result?.substring(0, 100)}...]`
        }
        scrollToBottom()
      } else if (data.type === 'error') {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = data.content
        lastMsg.loading = false
        lastMsg.error = true
      }
    },
    onDone: () => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      if (lastMsg.loading) {
        lastMsg.loading = false
      }
      agentStore.setLoading(false)
      agentStore.abortController = null
    },
    onError: (err) => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = `抱歉，处理出错了：${err.message}`
      lastMsg.loading = false
      lastMsg.error = true
      agentStore.setLoading(false)
      agentStore.abortController = null
      ElMessage.error('对话请求失败，请重试')
    },
  })

  // 保存中断函数到 store
  agentStore.abortController = stop
}

/** 停止生成 */
function handleStop() {
  agentStore.abort()
  const lastMsg = agentStore.messages[agentStore.messages.length - 1]
  if (lastMsg?.loading) {
    lastMsg.loading = false
    lastMsg.content += '\n[已停止生成]'
  }
}

/** 触发文件选择框 */
function triggerFileInput() {
  fileInputRef.value?.click()
}

/** 文件选择回调 */
function handleFileSelect(event) {
  const file = event.target.files[0]
  if (file) {
    if (!isValidAttachment(file)) {
      ElMessage.warning('仅支持图片或 ZIP 文件')
      return
    }
    selectedFile.value = file
    ElMessage.info(`${file.name} 已选择`)
  }
  event.target.value = ''
}

/** 拖拽进入区域 */
function handleDragOver() {
  if (!agentStore.isLoading) {
    isDragging.value = true
  }
}

/** 拖拽释放文件 */
function handleDrop(event) {
  isDragging.value = false
  if (agentStore.isLoading) return
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  if (!isValidAttachment(file)) {
    ElMessage.warning('仅支持图片或 ZIP 文件')
    return
  }
  selectedFile.value = file
  ElMessage.info(`${file.name} 已选择`)
}

/**
 * 快捷单图检测流程：
 * 1. 用户点击“📷 单图检测”按钮
 * 2. 弹出文件选择框
 * 3. 选择图片后，调用 detectSingle API
 * 4. 将结果以“用户消息 + AI 结果卡片”的形式插入对话
 */
async function handleQuickDetect(type) {
  if (type === 'single') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.onchange = async (e) => {
      const file = e.target.files[0]
      if (!file) return

      agentStore.addMessage({
        role: 'user',
        content: `[快捷检测] ${file.name}`,
        image: file.name,
        imagePreview: URL.createObjectURL(file),
      })

      agentStore.addMessage({
        role: 'assistant',
        content: '正在检测中...',
        loading: true,
      })
      scrollToBottom()

      const formData = new FormData()
      formData.append('file', file)

      try {
        const result = await detectSingle(formData)
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        if (result.error) {
          lastMsg.content = `检测失败：${result.error}`
          lastMsg.error = true
        } else {
          lastMsg.content = `检测完成！发现 ${result.total_objects ?? 0} 个目标。`
          lastMsg.detectionResult = result
        }
        lastMsg.loading = false
      } catch (err) {
        console.error('[单图检测异常]', err)
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = `检测失败：${err.response?.data?.detail || err.message || '请重试'}`
        lastMsg.loading = false
        lastMsg.error = true
      }
      scrollToBottom()
    }
    input.click()
  } else if (type === 'batch') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*,.zip'
    input.multiple = true
    input.onchange = async (e) => {
      const files = Array.from(e.target.files)
      if (!files.length) return

      const isZip = files.some((f) => f.name.toLowerCase().endsWith('.zip'))
      const formData = new FormData()

      if (isZip && files.length === 1) {
        formData.append('file', files[0])
        agentStore.addMessage({
          role: 'user',
          content: `[快捷检测] ZIP：${files[0].name}`,
        })
      } else {
        files.forEach((f) => formData.append('files', f))
        const imagePreviews = files.map((f) => URL.createObjectURL(f))
        agentStore.addMessage({
          role: 'user',
          content: `[快捷检测] ${files.length} 张图片`,
          images: imagePreviews,
        })
      }

      agentStore.addMessage({
        role: 'assistant',
        content: '正在批量检测中...',
        loading: true,
      })
      scrollToBottom()

      try {
        const apiCall = isZip ? detectZip(formData) : detectBatch(formData)
        const result = await apiCall
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]

        if (result.error) {
          lastMsg.content = `批量检测失败：${result.error}`
          lastMsg.loading = false
          lastMsg.error = true
          return
        }

        const totalObjects = result.total_objects ?? 0
        lastMsg.content = `批量检测完成！共 ${totalObjects} 个目标。`
        lastMsg.loading = false
        lastMsg.detectionResult = result
      } catch (err) {
        console.error('[批量检测异常]', err)
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = `批量检测失败：${err.response?.data?.detail || err.message || '请重试'}`
        lastMsg.loading = false
        lastMsg.error = true
      }
      scrollToBottom()
    }
    input.click()
  }
}

onMounted(() => {
  // 页面加载时显示欢迎消息
  if (agentStore.messages.length === 0) {
    agentStore.addMessage({
      role: 'assistant',
      content:
        '你好！我是 RSOD 目标检测智能体助手。\n\n你可以：\n- 上传一张图片，让我帮你检测目标\n- 使用下方的快捷按钮直接触发检测\n- 用自然语言描述你的需求\n\n试试发一张图片给我吧！',
    })
  }
})
</script>

<style lang="scss" scoped>
.chat-page {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-radius: $border-radius-md;
  box-shadow: $shadow-sm;
  overflow: hidden;
}

/* ── 消息列表 ── */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: $spacing-lg;
}

.message-item {
  display: flex;
  margin-bottom: $spacing-md;

  &.message-user {
    justify-content: flex-end;
  }

  &.message-assistant {
    justify-content: flex-start;
  }
}

.message-bubble {
  max-width: 70%;
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-lg;
  line-height: 1.6;
  word-break: break-word;
}

.user-bubble {
  background: $primary-color;
  color: white;
  border-bottom-right-radius: $border-radius-sm;
}

.assistant-bubble {
  background: $bg-color;
  border: 1px solid #e4e7ed;
  border-bottom-left-radius: $border-radius-sm;

  &.is-error {
    border-color: $danger-color;
    color: $danger-color;
  }
}

.message-content {
  white-space: pre-wrap;
}

.markdown-body {
  :deep(p) {
    margin: 0 0 $spacing-xs;
  }
  :deep(h1),
  :deep(h2),
  :deep(h3) {
    margin-top: $spacing-sm;
    margin-bottom: $spacing-xs;
  }
  :deep(table) {
    border-collapse: collapse;
    width: 100%;
    margin: $spacing-sm 0;
  }
  :deep(th),
  :deep(td) {
    border: 1px solid #e4e7ed;
    padding: $spacing-xs $spacing-sm;
  }
  :deep(code) {
    background: rgba(0, 0, 0, 0.06);
    padding: 2px 4px;
    border-radius: 3px;
  }
}

.typing-indicator {
  display: flex;
  gap: $spacing-xs;
  padding: $spacing-xs 0;

  span {
    width: 6px;
    height: 6px;
    background: $text-secondary;
    border-radius: 50%;
    animation: typing 1.2s infinite;
  }

  span:nth-child(2) {
    animation-delay: 0.2s;
  }
  span:nth-child(3) {
    animation-delay: 0.4s;
  }
}

/* ── 工具调用信息 ── */
.tool-call-info {
  margin-top: $spacing-sm;
}

/* ── 快捷操作栏 ── */
.quick-actions {
  display: flex;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-lg;
  border-top: 1px solid #ebeef5;
  background: #fff;
}

/* ── 输入区域 ── */
.input-area {
  padding: $spacing-md $spacing-lg;
  border-top: 1px solid #ebeef5;
  background: #fff;
}

.input-row {
  display: flex;
  align-items: center;
  gap: $spacing-sm;

  .el-input {
    flex: 1;
  }
}

.attach-btn {
  flex-shrink: 0;
}

/* ── 已选文件预览 ── */
.selected-file-chip {
  display: inline-flex;
  align-items: center;
  gap: $spacing-xs;
  max-width: 260px;
  margin-bottom: $spacing-sm;
  padding: 4px 10px;
  background: $bg-color;
  border: 1px solid #e4e7ed;
  border-radius: $border-radius-sm;
  font-size: 13px;
  color: $text-regular;

  .remove-icon {
    cursor: pointer;
    color: $text-secondary;

    &:hover {
      color: $danger-color;
    }
  }
}

/* ── 附件预览 ── */
.message-attachment {
  margin-top: $spacing-sm;

  img {
    max-width: 200px;
    border-radius: $border-radius-sm;
    border: 1px solid rgba(255, 255, 255, 0.4);
  }
}

/* ── 多图附件网格 ── */
.message-attachments-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: $spacing-sm;
  margin-top: $spacing-sm;

  img {
    width: 100%;
    height: 80px;
    object-fit: cover;
    border-radius: $border-radius-sm;
    border: 1px solid rgba(255, 255, 255, 0.4);
  }
}

/* ── 拖拽遮罩 ── */
.drag-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(64, 158, 255, 0.08);
  border: 2px dashed $primary-color;
  pointer-events: none;
  z-index: 10;
}

.drag-overlay-content {
  text-align: center;
  color: $primary-color;
  font-size: 15px;

  .el-icon {
    font-size: 40px;
    margin-bottom: $spacing-sm;
  }
}

@keyframes typing {
  0%,
  60%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-4px);
  }
}
</style>
