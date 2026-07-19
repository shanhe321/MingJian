<template>
  <div
    class="chat-page"
    :class="{ 'is-empty': !hasUserMessages }"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="handleDrop"
  >
    <div v-if="agentStore.sessionLoading" class="session-loading-state">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>正在载入会话...</span>
    </div>
    <ChatWelcome v-else-if="!hasUserMessages" @use-prompt="handleUsePrompt" />

    <!-- ── 消息列表区域 ── -->
    <div v-else class="message-list" ref="messageListRef" @scroll.passive="handleMessageScroll">
      <div
        v-for="(msg, index) in agentStore.messages"
        :key="msg.id ?? index"
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
          <!-- 视频附件（视频检测） -->
          <div v-if="msg.videoUrl" class="message-attachment">
            <video :src="msg.videoUrl" controls preload="metadata"></video>
          </div>
        </div>

        <!-- AI 消息 -->
        <div
          v-else-if="msg.role === 'assistant'"
          :class="['message-bubble', 'assistant-bubble', { 'is-error': msg.error }]"
        >
          <!-- 思考中 / 打字动画（尚无任何内容、工具调用或思考文案时展示） -->
          <div v-if="msg.loading && !msg.content && !msg.toolCalls?.length && !msg.statusText" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
          <!-- Agent 思考过程提示 -->
          <div v-else-if="msg.loading && !msg.content && msg.statusText" class="thinking-hint">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>{{ msg.statusText }}</span>
          </div>
          <div v-else class="message-content markdown-body" v-html="renderMarkdown(msg.content)"></div>

          <!-- 工具调用可视化：loading → done -->
          <div v-if="msg.toolCalls && msg.toolCalls.length > 0" class="tool-calls">
            <div
              v-for="(tc, idx) in msg.toolCalls"
              :key="idx"
              class="tool-call-item"
              :class="{ 'is-loading': tc.status === 'loading' }"
            >
              <el-icon v-if="tc.status === 'loading'" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="tc.status === 'error'" color="#f56c6c"><CircleClose /></el-icon>
              <el-icon v-else color="#67c23a"><CircleCheckFilled /></el-icon>
              <span class="tool-name">{{ getToolName(tc.tool) }}</span>
              <span class="tool-arrow">→</span>
              <span
                class="tool-summary"
                :class="{ success: tc.status === 'done', error: tc.status === 'error' }"
              >
                {{ tc.summary || (tc.status === 'loading' ? '执行中...' : '完成') }}
              </span>
            </div>
          </div>

          <!-- 知识库检索结果标注 -->
          <div v-if="msg.hasKnowledge === true" class="knowledge-badge success">
            <el-icon><CircleCheckFilled /></el-icon>
            <span>📚 本次回答参考了知识库检索结果</span>
          </div>
          <div v-else-if="msg.hasKnowledge === false" class="knowledge-badge empty">
            <el-icon><InfoFilled /></el-icon>
            <span>💡 知识库中暂无相关内容，回答来自大模型</span>
          </div>

          <!-- 检测结果卡片（快捷检测按钮走此路径展示） -->
          <DetectionResultCard v-if="msg.detectionResult" :result="msg.detectionResult" />

          <!-- 错误重试 -->
          <div v-if="msg.error" class="error-retry">
            <el-button size="small" type="danger" plain @click="retryMessage(msg)">
              <el-icon><RefreshRight /></el-icon>
              重新发送
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <ChatInputBar
      ref="chatInputRef"
      v-model="inputText"
      :mode-value="detectionMode"
      :current-mode="currentMode"
      :selected-files="selectedFiles"
      :preview-url="selectedPreviewUrl"
      :file-title="fileSummaryTitle"
      :file-meta="fileSummaryMeta"
      :file-extra="fileExtraText"
      :loading="composerBusy"
      :stoppable="agentStore.isLoading"
      :can-send="canSend"
      :has-messages="agentStore.messages.length > 0"
      @update:mode-value="changeDetectionMode"
      @file-select="handleFileSelect"
      @clear-files="clearSelectedFiles"
      @send="sendMessage"
      @stop="handleStop"
      @new-chat="handleNewChat"
    />

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
 * ChatPage.vue — 智能对话界面（Day 11：流式渲染优化 + 工具调用可视化）
 *
 * 功能：
 *   - 消息气泡（用户/AI 区分）
 *   - 文件附件上传（图片/ZIP 拖拽或选择）
 *   - SSE 流式渲染 AI 回复，展示思考过程 / 工具调用 loading → done 状态
 *   - 跨轮次对话记忆（携带 session_id，支持“再检测一张”等上下文表达）
 *   - 知识库检索结果标注（是否命中知识库）
 *   - 检测结果卡片展示（快捷按钮路径）
 *   - 快捷操作栏（单图/批量/视频/摄像头）+ 清空对话
 *   - 中断当前对话 / 出错后一键重试
 */
import { detectBatch, detectSingle, detectVideo, detectZip, getDetectionStatus, getVideoStatus } from '@/api/detection'
import { clearChatSession, uploadChatImage } from '@/api/chat'
import ChatInputBar from '@/components/chat/ChatInputBar.vue'
import ChatWelcome from '@/components/chat/ChatWelcome.vue'
import DetectionResultCard from '@/components/DetectionResultCard.vue'
import { useAgentStore } from '@/stores/agent'
import { renderMarkdown } from '@/utils/markdown'
import { isNearScrollBottom } from '@/utils/chatScroll'
import { streamChat, TOOL_NAME_MAP } from '@/utils/stream'
import {
  CircleCheckFilled,
  CircleClose,
  Files,
  Folder,
  FolderOpened,
  InfoFilled,
  Loading,
  Picture,
  RefreshRight,
  UploadFilled,
  VideoCamera,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

// ── Store ──
const agentStore = useAgentStore()

// ── 响应式状态 ──
const inputText = ref('')
const selectedFiles = ref([])
const selectedPreviewUrl = ref('')
const detectionMode = ref('single')
const messageListRef = ref(null)
const chatInputRef = ref(null)
const isDragging = ref(false)
const isDetectionRunning = ref(false)
const shouldFollowStream = ref(true)
let messageIdSeq = 0
const messageObjectUrls = new Set()

const detectionModes = {
  single: {
    label: '单图检测',
    icon: Picture,
    accept: 'image/*',
    multiple: false,
    placeholder: '描述你的检测需求，或上传一张 PCB 图片...',
  },
  batch: {
    label: '批量图片',
    icon: Files,
    accept: 'image/*',
    multiple: true,
    placeholder: '上传多张 PCB 图片进行批量检测...',
  },
  zip: {
    label: 'ZIP 检测',
    icon: Folder,
    accept: '.zip,application/zip',
    multiple: false,
    placeholder: '上传一个 ZIP 压缩包进行异步检测...',
  },
  folder: {
    label: '文件夹检测',
    icon: FolderOpened,
    accept: 'image/*',
    multiple: true,
    placeholder: '选择包含 PCB 图片的文件夹进行异步检测...',
  },
  video: {
    label: '视频检测',
    icon: VideoCamera,
    accept: 'video/mp4,video/avi,video/quicktime,video/x-msvideo,video/x-matroska,video/x-ms-wmv,video/x-flv,.mp4,.avi,.mov,.mkv,.wmv,.flv',
    multiple: false,
    placeholder: '上传视频文件并分析采样帧...',
  },
}

// ── 计算属性 ──
const currentMode = computed(() => detectionModes[detectionMode.value] || detectionModes.single)
const composerBusy = computed(() => agentStore.isLoading || agentStore.sessionLoading || isDetectionRunning.value)

const canSend = computed(() => {
  return !composerBusy.value
    && (inputText.value.trim() || selectedFiles.value.length)
})

const hasUserMessages = computed(() => {
  return agentStore.messages.some((msg) => msg.role === 'user')
})

const fileSummaryTitle = computed(() => {
  if (!selectedFiles.value.length) return ''
  if (['batch', 'folder'].includes(detectionMode.value)) {
    if (detectionMode.value === 'folder') return `${selectedFiles.value.length} 张文件夹图片`
    return `${selectedFiles.value.length} 个文件`
  }
  return selectedFiles.value[0].name
})

const fileSummaryMeta = computed(() => {
  if (!selectedFiles.value.length) return ''
  if (['batch', 'folder'].includes(detectionMode.value) && selectedFiles.value.length > 1) {
    const totalSize = selectedFiles.value.reduce((sum, file) => sum + file.size, 0)
    return `${selectedFiles.value.length} 个文件，${formatFileSize(totalSize)}`
  }
  const file = selectedFiles.value[0]
  return `${formatFileSize(file.size)}${file.type ? ` · ${file.type}` : ''}`
})

const fileExtraText = computed(() => {
  if (!['batch', 'folder'].includes(detectionMode.value) || selectedFiles.value.length <= 3) return ''
  return `已选择 ${selectedFiles.value.length} 个文件`
})

/** 校验文件类型是否为图片或 ZIP */
function isValidAttachment(file, mode = detectionMode.value) {
  const lowerName = file.name.toLowerCase()
  if (mode === 'single') {
    return file.type.startsWith('image/')
  }
  if (mode === 'batch') {
    return file.type.startsWith('image/')
  }
  if (mode === 'zip') return lowerName.endsWith('.zip')
  if (mode === 'folder') return file.type.startsWith('image/')
  if (mode === 'video') {
    return ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv'].some((ext) => lowerName.endsWith(ext))
  }
  return false
}

function formatFileSize(size) {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function updateSelectedPreview() {
  if (selectedPreviewUrl.value) {
    URL.revokeObjectURL(selectedPreviewUrl.value)
    selectedPreviewUrl.value = ''
  }
  const firstFile = selectedFiles.value[0]
  if (firstFile && detectionMode.value === 'single' && firstFile.type.startsWith('image/')) {
    selectedPreviewUrl.value = URL.createObjectURL(firstFile)
  }
}

function clearSelectedFiles() {
  selectedFiles.value = []
  updateSelectedPreview()
}

function createMessageObjectUrl(file) {
  const url = URL.createObjectURL(file)
  messageObjectUrls.add(url)
  return url
}

function revokeMessageObjectUrls() {
  messageObjectUrls.forEach((url) => URL.revokeObjectURL(url))
  messageObjectUrls.clear()
}

function changeDetectionMode(mode) {
  detectionMode.value = mode
  clearSelectedFiles()
}

function handleUsePrompt(prompt) {
  inputText.value = prompt
  chatInputRef.value?.focus()
}

/** 滚动到底部 */
function scrollToBottom(force = false) {
  if (!force && !shouldFollowStream.value) return
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
      shouldFollowStream.value = true
    }
  })
}

function handleMessageScroll() {
  shouldFollowStream.value = isNearScrollBottom(messageListRef.value)
}

/** 生成带唯一 id 的消息并加入会话（用于精确定位重试目标，避免依赖“最后一条消息”） */
function pushMessage(message) {
  const withId = { id: `msg-${Date.now()}-${messageIdSeq++}`, ...message }
  return agentStore.addMessage(withId)
}

/** 工具名称中文映射（沿用 stream.js 中的统一映射） */
function getToolName(toolKey) {
  return TOOL_NAME_MAP[toolKey] || toolKey
}

/**
 * 发起一次 Agent 对话流式请求
 *
 * @param {Object} requestBody - 请求体（message / image_path / session_id）
 * @param {Object} assistantMsg - 承载本次回复的 AI 消息对象（通过引用直接修改，兼容重试场景）
 */
function runChatStream(requestBody, assistantMsg) {
  assistantMsg.content = ''
  assistantMsg.loading = true
  assistantMsg.error = false
  assistantMsg.statusText = ''
  assistantMsg.toolCalls = []
  assistantMsg.hasKnowledge = undefined
  assistantMsg.detectionResult = null
  assistantMsg.retryPayload = requestBody

  agentStore.setLoading(true)
  shouldFollowStream.value = true
  scrollToBottom(true)

  let fullContent = ''

  const stop = streamChat('/api/chat/stream', requestBody, {
    onMessage: (data) => {
      if (data.type === 'thinking') {
        assistantMsg.statusText = data.content || '正在思考...'
      } else if (data.type === 'tool_start') {
        assistantMsg.statusText = `正在调用${getToolName(data.tool)}...`
        assistantMsg.toolCalls.push({ tool: data.tool, status: 'loading', summary: '' })
      } else if (data.type === 'tool_end') {
        const tc = [...assistantMsg.toolCalls].reverse().find((t) => t.tool === data.tool && t.status === 'loading')
        if (tc) {
          tc.summary = describeToolResult(data.tool, data.summary)
          tc.status = data.summary && data.summary.startsWith('{"error"') ? 'error' : 'done'
        }
        if (data.tool === 'search_knowledge') {
          if (data.summary && data.summary.includes('暂无相关内容')) {
            assistantMsg.hasKnowledge = false
          } else if (data.summary && data.summary.includes('"knowledge"')) {
            assistantMsg.hasKnowledge = true
          }
        }
        assistantMsg.statusText = '正在分析查询结果...'
        scrollToBottom()
      } else if (data.type === 'text_chunk') {
        assistantMsg.statusText = ''
        fullContent += data.content
        assistantMsg.content = fullContent
        scrollToBottom()
      } else if (data.type === 'error') {
        assistantMsg.content = data.content
        assistantMsg.loading = false
        assistantMsg.error = true
      }
      // done 事件仅携带 full_text 汇总信息，文本已通过 text_chunk 逐字渲染，无需额外处理
    },
    onDone: () => {
      assistantMsg.loading = false
      assistantMsg.statusText = ''
      agentStore.setLoading(false)
      agentStore.abortController = null
      agentStore.refreshSessions().catch(() => {})
    },
    onError: (err) => {
      assistantMsg.content = assistantMsg.content || `抱歉，处理出错了：${err.message}`
      assistantMsg.loading = false
      assistantMsg.error = true
      agentStore.setLoading(false)
      agentStore.abortController = null
      ElMessage.error('对话请求失败，请重试')
    },
  })

  agentStore.abortController = stop
}

/**
 * 尽量从被截断的工具结果摘要中提炼出人类可读的展示文案。
 * 后端出于流量考虑只回传前 100 个字符，无法保证是合法 JSON，因此只做“最大努力”识别。
 */
function describeToolResult(tool, summary) {
  if (!summary) return '完成'
  if (summary.startsWith('{"error"')) return '执行失败'
  if (tool === 'search_knowledge') {
    if (summary.includes('暂无相关内容')) return '知识库中暂无相关内容'
    if (summary.includes('"knowledge"')) return '检索成功'
  }
  return '完成'
}

/** 发送消息 */
async function sendMessage() {
  if (!canSend.value) return

  const message = inputText.value.trim()
  const filesToSend = [...selectedFiles.value]

  if (filesToSend.length && (!message || detectionMode.value !== 'single')) {
    inputText.value = ''
    clearSelectedFiles()
    isDetectionRunning.value = true
    try {
      if (detectionMode.value === 'single') {
        await runSingleDetection(filesToSend[0])
      } else if (detectionMode.value === 'batch') {
        await runBatchDetection(filesToSend)
      } else if (detectionMode.value === 'zip') {
        await runZipDetection(filesToSend[0])
      } else if (detectionMode.value === 'folder') {
        await runFolderDetection(filesToSend)
      } else if (detectionMode.value === 'video') {
        await runVideoDetection(filesToSend[0])
      }
    } finally {
      isDetectionRunning.value = false
      chatInputRef.value?.focus()
    }
    return
  }

  // ── 关键：在清空之前保存文件引用 ──
  const fileToSend = filesToSend[0]
  const imagePreview = fileToSend && fileToSend.type.startsWith('image/')
    ? createMessageObjectUrl(fileToSend)
    : null

  // 添加用户消息到列表
  pushMessage({
    role: 'user',
    content: message || (fileToSend ? `[附件] ${fileToSend.name}` : ''),
    image: fileToSend ? fileToSend.name : null,
    imagePreview,
  })

  // 清空输入
  inputText.value = ''
  clearSelectedFiles()

  // 添加 AI 加载占位
  const assistantMsg = pushMessage({
    role: 'assistant',
    content: '',
    loading: true,
    toolCalls: [],
  })

  agentStore.setLoading(true)
  shouldFollowStream.value = true
  scrollToBottom(true)

  // ── 如果有附件图片，先上传到服务端获取真实路径 ──
  let serverImagePath = null
  if (fileToSend) {
    try {
      const formData = new FormData()
      formData.append('file', fileToSend)
      // 不设置 Content-Type，让 axios 自动添加 boundary
      const uploadResult = await uploadChatImage(formData)
      serverImagePath = uploadResult.image_path
    } catch (err) {
      console.error('[图片上传失败]', err.response?.data || err.message || err)
      assistantMsg.content = `图片上传失败：${err.response?.data?.detail || err.message || '未知错误'}，请重试`
      assistantMsg.loading = false
      assistantMsg.error = true
      agentStore.setLoading(false)
      return
    }
  }

  // 发起 SSE 流式请求（携带 session_id 以支持跨轮次对话记忆）
  const requestBody = {
    message: message || '检测这张图片',
    session_id: agentStore.ensureSessionId(),
    ...(serverImagePath ? { image_path: serverImagePath } : {}),
  }

  runChatStream(requestBody, assistantMsg)
}

/** 出错后重新发送同一请求（沿用原有 session_id / 附件路径，不重复上传文件） */
function retryMessage(assistantMsg) {
  if (!assistantMsg.retryPayload || agentStore.isLoading) return
  runChatStream(assistantMsg.retryPayload, assistantMsg)
}

/** 停止生成 */
function handleStop() {
  agentStore.abort()
  const lastMsg = agentStore.messages[agentStore.messages.length - 1]
  if (lastMsg?.loading) {
    lastMsg.loading = false
    lastMsg.statusText = ''
    lastMsg.content += '\n[已停止生成]'
  }
}

/** 清空当前对话记忆并开启新会话 */
async function handleNewChat() {
  if (agentStore.messages.length === 0) return
  try {
    await ElMessageBox.confirm('确定要清空当前对话吗？清空后无法恢复上下文记忆。', '清空对话', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  if (agentStore.currentSessionId) {
    try {
      await clearChatSession(agentStore.currentSessionId)
    } catch (err) {
      console.warn('[清空会话记忆失败]', err.message || err)
    }
  }

  agentStore.newChat()
  await agentStore.refreshSessions().catch(() => {})
  ElMessage.success('对话已清空')
}

function applySelectedFiles(fileList) {
  const files = Array.from(fileList || [])
  if (!files.length) return

  const mode = detectionMode.value
  const normalizedFiles = ['batch', 'folder'].includes(mode) ? files : [files[0]]
  if (mode === 'folder' && normalizedFiles.some((file) => !file.type.startsWith('image/'))) {
    ElMessage.warning('文件夹检测仅支持图片文件')
    return
  }

  for (const file of normalizedFiles) {
    if (!isValidAttachment(file, mode)) {
      ElMessage.warning(fileTypeWarning(mode))
      return
    }
    if (mode === 'video' && file.size > 50 * 1024 * 1024) {
      ElMessage.warning('视频文件不能超过 50MB')
      return
    }
  }

  selectedFiles.value = normalizedFiles
  updateSelectedPreview()
  ElMessage.info(selectionMessage(normalizedFiles, mode))
}

function fileTypeWarning(mode) {
  if (mode === 'single') return '单图检测仅支持图片文件'
  if (mode === 'batch') return '批量检测仅支持图片文件'
  if (mode === 'zip') return 'ZIP 检测仅支持一个 .zip 压缩包'
  if (mode === 'folder') return '文件夹检测仅支持图片文件'
  if (mode === 'video') return '视频检测仅支持 mp4、avi、mov、mkv、wmv、flv'
  return '当前模式不需要上传文件'
}

function selectionMessage(files, mode) {
  if (mode === 'batch') {
    return `已选择 ${files.length} 个文件`
  }
  if (mode === 'zip') return `${files[0].name} 已选择`
  if (mode === 'folder') return `已选择文件夹中的 ${files.length} 张图片`
  return `${files[0].name} 已选择`
}

/** 文件选择回调 */
function handleFileSelect(event) {
  applySelectedFiles(event.target.files)
  event.target.value = ''
}

/** 拖拽进入区域 */
function handleDragOver() {
  if (!composerBusy.value) {
    isDragging.value = true
  }
}

/** 拖拽释放文件 */
function handleDrop(event) {
  isDragging.value = false
  if (composerBusy.value) return
  const files = event.dataTransfer?.files
  if (!files?.length) return
  applySelectedFiles(files)
}

async function runSingleDetection(file) {
  if (!file) return
  if (!isValidAttachment(file, 'single')) {
    ElMessage.warning(fileTypeWarning('single'))
    return
  }

  pushMessage({
    role: 'user',
    content: `[快捷检测] ${file.name}`,
    image: file.name,
    imagePreview: createMessageObjectUrl(file),
  })

  const assistantMsg = pushMessage({
    role: 'assistant',
    content: '正在检测中...',
    loading: true,
  })
  shouldFollowStream.value = true
  scrollToBottom(true)

  const formData = new FormData()
  formData.append('file', file)

  try {
    const result = await detectSingle(formData)
    if (result.error) {
      assistantMsg.content = `检测失败：${result.error}`
      assistantMsg.error = true
    } else {
      assistantMsg.content = `检测完成！发现 ${result.total_objects ?? 0} 个目标。`
      assistantMsg.detectionResult = result
    }
    assistantMsg.loading = false
  } catch (err) {
    console.error('[单图检测异常]', err)
    assistantMsg.content = `检测失败：${err.response?.data?.detail || err.message || '请重试'}`
    assistantMsg.loading = false
    assistantMsg.error = true
  }
  scrollToBottom()
}

async function runBatchDetection(files) {
  if (!files?.length) return
  if (files.some((file) => !isValidAttachment(file, 'batch'))) {
    ElMessage.warning(fileTypeWarning('batch'))
    return
  }

  const formData = new FormData()
  files.forEach((f) => formData.append('files', f))
  const imagePreviews = files.map((f) => createMessageObjectUrl(f))
  pushMessage({
    role: 'user',
    content: `[批量检测] ${files.length} 张图片`,
    images: imagePreviews,
  })

  const assistantMsg = pushMessage({
    role: 'assistant',
    content: '正在批量检测中...',
    loading: true,
  })
  shouldFollowStream.value = true
  scrollToBottom(true)

  try {
    const result = await detectBatch(formData)

    if (result.error) {
      assistantMsg.content = `批量检测失败：${result.error}`
      assistantMsg.loading = false
      assistantMsg.error = true
      return
    }

    const totalObjects = result.total_objects ?? 0
    assistantMsg.content = `批量检测完成！共 ${totalObjects} 个目标。`
    assistantMsg.loading = false
    assistantMsg.detectionResult = result
  } catch (err) {
    console.error('[批量检测异常]', err)
    assistantMsg.content = `批量检测失败：${err.response?.data?.detail || err.message || '请重试'}`
    assistantMsg.loading = false
    assistantMsg.error = true
  }
  scrollToBottom()
}

async function runZipDetection(file) {
  if (!file) return
  if (!isValidAttachment(file, 'zip')) {
    ElMessage.warning(fileTypeWarning('zip'))
    return
  }

  const formData = new FormData()
  formData.append('file', file)
  pushMessage({ role: 'user', content: `[ZIP 检测] ${file.name}` })
  const assistantMsg = pushMessage({
    role: 'assistant',
    content: '正在提交 ZIP 检测...',
    loading: true,
  })
  shouldFollowStream.value = true
  scrollToBottom(true)

  try {
    const result = await detectZip(formData)
    if (result.error) {
      assistantMsg.content = `ZIP 检测失败：${result.error}`
      assistantMsg.error = true
    } else {
      assistantMsg.content = `ZIP 检测完成！共发现 ${result.total_objects ?? 0} 个目标。`
      assistantMsg.detectionResult = result
    }
  } catch (err) {
    assistantMsg.content = `ZIP 检测失败：${err.response?.data?.detail || err.message || '请重试'}`
    assistantMsg.error = true
  } finally {
    assistantMsg.loading = false
    scrollToBottom()
  }
}

async function runFolderDetection(files) {
  if (!files?.length) return
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file, file.webkitRelativePath || file.name))
  formData.append('mode', 'folder')
  formData.append('async_mode', 'true')
  pushMessage({ role: 'user', content: `[文件夹检测] ${files.length} 张图片` })
  const assistantMsg = pushMessage({ role: 'assistant', content: '文件夹任务正在提交...', loading: true })
  shouldFollowStream.value = true
  scrollToBottom(true)
  try {
    const task = await detectBatch(formData)
    await pollFolderProgress(task.task_id, assistantMsg)
  } catch (err) {
    assistantMsg.content = `文件夹检测失败：${err.response?.data?.detail || err.message || '请重试'}`
    assistantMsg.loading = false
    assistantMsg.error = true
  }
}

async function pollFolderProgress(taskId, assistantMsg, maxAttempts = 240) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const status = await getDetectionStatus(taskId)
    assistantMsg.content = `文件夹检测：${status.processed_items}/${status.total_items}，失败 ${status.failed_items}，进度 ${status.progress}%`
    if (status.status === 'completed') {
      assistantMsg.content += '\n检测完成，可在历史记录中查看逐文件结果和报告。'
      assistantMsg.loading = false
      return
    }
    if (status.status === 'failed') {
      assistantMsg.content += `\n任务失败：${status.error_message || '未知错误'}`
      assistantMsg.loading = false
      assistantMsg.error = true
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }
  assistantMsg.content = '文件夹检测仍在后台执行，请稍后在历史记录中查看。'
  assistantMsg.loading = false
}

async function runVideoDetection(file) {
  if (!file) return
  if (!isValidAttachment(file, 'video')) {
    ElMessage.warning(fileTypeWarning('video'))
    return
  }

  // 校验文件大小（50MB）
  const maxSize = 50 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.warning('视频文件不能超过 50MB')
    return
  }

  // 创建视频的 Blob URL 用于预览
  const videoUrl = createMessageObjectUrl(file)

  pushMessage({
    role: 'user',
    content: `[视频检测] ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)}MB)`,
    videoUrl,
  })

  const assistantMsg = pushMessage({
    role: 'assistant',
    content: '正在上传视频...',
    loading: true,
  })
  shouldFollowStream.value = true
  scrollToBottom(true)

  // 上传视频
  const formData = new FormData()
  formData.append('file', file)

  try {
    const uploadResult = await detectVideo(formData)
    const taskId = uploadResult.task_id

    assistantMsg.content = '视频已上传，正在处理中...'

    // 开始轮询进度
    await pollVideoProgress(taskId, assistantMsg)
  } catch (err) {
    console.error('[视频检测失败]', err)
    assistantMsg.content = `视频检测失败：${err.response?.data?.detail || err.message || '请重试'}`
    assistantMsg.loading = false
    assistantMsg.error = true
  }
  scrollToBottom()
}

/**
 * 轮询视频检测进度
 * @param {number} taskId - 视频检测任务 ID
 * @param {Object} assistantMsg - 承载检测状态的 AI 消息对象
 * @param {number} intervalMs - 轮询间隔（毫秒）
 * @param {number} maxAttempts - 最大轮询次数（防止无限轮询）
 */
async function pollVideoProgress(taskId, assistantMsg, intervalMs = 1500, maxAttempts = 120) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const status = await getVideoStatus(taskId)

      if (status.status === 'completed') {
        const result = status.result || {}
        assistantMsg.content = status.message || `视频检测完成！共发现 ${result.total_objects ?? 0} 个目标。`
        assistantMsg.detectionResult = { ...result, type: 'video' }
        assistantMsg.loading = false
        scrollToBottom()
        return
      }

      if (status.status === 'failed') {
        assistantMsg.content = `视频检测失败：${status.message || '未知错误'}`
        assistantMsg.loading = false
        assistantMsg.error = true
        scrollToBottom()
        return
      }

      // 仍在处理中，更新进度提示
      const progress = status.progress ?? 0
      assistantMsg.content = `视频处理中...${progress ? ` (${progress}%)` : ''}`
      scrollToBottom()
    } catch (err) {
      console.error('[视频进度查询失败]', err)
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }

  // 超过最大轮询次数仍未完成
  assistantMsg.content = '视频处理超时，请稍后在历史记录中查看结果'
  assistantMsg.loading = false
  assistantMsg.error = true
  scrollToBottom()
}

watch(
  () => agentStore.currentSessionId,
  () => {
    shouldFollowStream.value = true
    scrollToBottom(true)
  },
)

watch(
  () => agentStore.focusRequestId,
  () => {
    revokeMessageObjectUrls()
    chatInputRef.value?.focus()
  },
)

watch(
  () => agentStore.sessionLoading,
  (loading) => {
    if (loading) {
      revokeMessageObjectUrls()
    } else {
      shouldFollowStream.value = true
      scrollToBottom(true)
    }
  },
)

onMounted(() => chatInputRef.value?.focus())

onBeforeUnmount(() => {
  agentStore.abort()
  clearSelectedFiles()
  revokeMessageObjectUrls()
})
</script>

<style lang="scss" scoped>
.chat-page {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  width: 100%;
  max-width: none;
  margin: 0 auto;
  padding: 0 12px 12px;
  background: transparent;
  overflow: hidden;
  box-sizing: border-box;
}

.chat-page.is-empty {
  justify-content: flex-end;

  :deep(.chat-input-shell) {
    margin-bottom: clamp(16px, 4vh, 44px);
  }
}

/* ── 消息列表 ── */
.message-list {
  flex: 1;
  min-height: 0;
  width: min(980px, 100%);
  margin: 0 auto;
  overflow-y: auto;
  padding: $spacing-lg $spacing-md $spacing-md;
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
  max-width: min(760px, 78%);
  padding: 10px 14px;
  border-radius: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.user-bubble {
  background: rgba(232, 237, 247, 0.84);
  color: $text-primary;
  border: 1px solid rgba(199, 210, 228, 0.6);
  border-bottom-right-radius: 6px;
}

.session-loading-state {
  display: flex;
  min-height: 0;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: $text-secondary;
  font-size: 13px;

  .el-icon {
    color: $primary-color;
  }
}

.assistant-bubble {
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(218, 226, 238, 0.62);
  color: $text-regular;
  border-bottom-left-radius: 6px;

  &.is-error {
    border-color: rgba(220, 90, 90, 0.3);
    background: rgba(254, 242, 242, 0.9);
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
    border: 1px solid $border-color;
    padding: $spacing-xs $spacing-sm;
  }
  :deep(code) {
    background: #eef2f7;
    padding: 2px 4px;
    border-radius: 3px;
  }
  :deep(img) {
    max-width: 100%;
    border-radius: $border-radius-sm;
    margin: $spacing-xs 0;
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

/* ── Agent 思考过程提示 ── */
.thinking-hint {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  color: $text-secondary;
  font-size: 13px;

  .is-loading {
    animation: rotating 1s linear infinite;
  }
}

/* ── 工具调用可视化 ── */
.tool-calls {
  margin-top: $spacing-sm;
  padding: $spacing-xs $spacing-sm;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(241, 245, 251, 0.72));
  border-radius: $border-radius-sm;
  border: 1px solid $border-color;
}

.tool-call-item {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  padding: 4px 0;
  font-size: 13px;
  color: $text-regular;

  &.is-loading {
    color: $primary-color;
  }

  .is-loading {
    animation: rotating 1s linear infinite;
  }

  .tool-name {
    font-weight: 600;
  }

  .tool-arrow {
    color: $text-secondary;
  }

  .tool-summary {
    color: $text-secondary;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 260px;

    &.success {
      color: $success-color;
    }

    &.error {
      color: $danger-color;
    }
  }
}

/* ── 知识库检索标注 ── */
.knowledge-badge {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  margin-top: $spacing-sm;
  padding: 4px $spacing-sm;
  border-radius: $border-radius-sm;
  font-size: 12px;
  width: fit-content;

  &.success {
    background: rgba(22, 163, 104, 0.1);
    color: $success-color;
  }

  &.empty {
    background: rgba(102, 112, 133, 0.1);
    color: $text-secondary;
  }
}

/* ── 出错重试 ── */
.error-retry {
  margin-top: $spacing-sm;
}

/* ── 附件预览 ── */
.message-attachment {
  margin-top: $spacing-sm;

  img {
    max-width: 200px;
    border-radius: $border-radius-sm;
    border: 1px solid rgba(148, 163, 184, 0.22);
  }

  video {
    max-width: 240px;
    max-height: 180px;
    border-radius: $border-radius-sm;
    border: 1px solid rgba(148, 163, 184, 0.22);
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
    border: 1px solid rgba(148, 163, 184, 0.22);
  }
}

/* ── 拖拽遮罩 ── */
.drag-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(91, 124, 250, 0.08);
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

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .message-bubble {
    max-width: 88%;
  }

}
</style>
