<template>
  <div
    class="chat-page"
    :class="{ 'is-empty': !hasUserMessages }"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="handleDrop"
  >
    <ChatWelcome v-if="!hasUserMessages" @use-prompt="handleUsePrompt" />

    <!-- ── 消息列表区域 ── -->
    <div v-else class="message-list" ref="messageListRef">
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

    <!-- ── 输入区域 ── -->
    <div class="input-area">
      <div class="session-toolbar">
        <el-select v-model="selectedSessionId" placeholder="历史会话" clearable filterable @change="loadSessionHistory">
          <el-option
            v-for="session in agentStore.sessions"
            :key="session.session_id"
            :label="session.title || session.session_id"
            :value="session.session_id"
          />
        </el-select>
        <el-button text @click="loadSessions">刷新会话</el-button>
        <el-button text @click="startNewSession">新建会话</el-button>
      </div>
      <!-- 已选文件预览 -->
      <div v-if="selectedFiles.length" class="selected-file-panel">
        <div class="selected-file-main">
          <img v-if="selectedPreviewUrl" :src="selectedPreviewUrl" alt="已选图片预览" />
          <span v-else class="selected-file-icon">
            <el-icon><component :is="currentMode.icon" /></el-icon>
          </span>
          <span class="selected-file-copy">
            <strong>{{ fileSummaryTitle }}</strong>
            <small>{{ fileSummaryMeta }}</small>
            <small v-if="fileExtraText">{{ fileExtraText }}</small>
          </span>
        </div>
        <button type="button" class="remove-file-btn" aria-label="移除已选文件" @click="clearSelectedFiles">
          <el-icon><Close /></el-icon>
        </button>
      </div>

      <div v-if="selectedFiles.length > 1" class="selected-file-list">
        <span v-for="file in selectedFiles.slice(0, 3)" :key="file.name">{{ file.name }}</span>
        <span v-if="selectedFiles.length > 3">还有 {{ selectedFiles.length - 3 }} 个</span>
      </div>

      <div class="input-row">
        <!-- 附件按钮 -->
        <el-button
          class="attach-btn"
          circle
          :disabled="agentStore.isLoading || detectionMode === 'camera'"
          @click="triggerFileInput"
        >
          <el-icon><Paperclip /></el-icon>
        </el-button>

        <DetectionModeSelector v-model="detectionMode" />

        <input
          ref="fileInputRef"
          type="file"
          :accept="currentMode.accept"
          :multiple="currentMode.multiple"
          :webkitdirectory="detectionMode === 'folder' ? '' : null"
          :directory="detectionMode === 'folder' ? '' : null"
          style="display: none"
          @change="handleFileSelect"
        />

        <!-- 文本输入框 -->
        <el-input
          v-model="inputText"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          resize="none"
          :placeholder="currentMode.placeholder"
          :disabled="agentStore.isLoading"
          @keydown.enter.exact.prevent="sendMessage"
        />

        <!-- 发送/停止按钮 -->
        <el-button
          v-if="!agentStore.isLoading"
          class="send-btn"
          type="primary"
          circle
          :disabled="!canSend"
          aria-label="发送"
          @click="sendMessage"
        >
          <el-icon><Position /></el-icon>
        </el-button>
        <el-button v-else class="stop-btn" type="danger" @click="handleStop">停止</el-button>

        <el-button
          v-if="agentStore.messages.length"
          class="clear-chat-btn"
          :disabled="agentStore.isLoading"
          text
          aria-label="清空对话"
          @click="handleNewChat"
        >
          <el-icon><Delete /></el-icon>
        </el-button>
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
import { clearChatSession, getChatSessionHistory, getChatSessions } from '@/api/chat'
import ChatWelcome from '@/components/chat/ChatWelcome.vue'
import DetectionModeSelector from '@/components/chat/DetectionModeSelector.vue'
import DetectionResultCard from '@/components/DetectionResultCard.vue'
import { useAgentStore } from '@/stores/agent'
import { renderMarkdown } from '@/utils/markdown'
import request from '@/utils/request'
import { streamChat, TOOL_NAME_MAP } from '@/utils/stream'
import {
  Camera,
  Close,
  CircleCheckFilled,
  CircleClose,
  Delete,
  FolderOpened,
  InfoFilled,
  Loading,
  Paperclip,
  Picture,
  Position,
  RefreshRight,
  UploadFilled,
  VideoCamera,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

// ── Store ──
const agentStore = useAgentStore()
const router = useRouter()

// ── 响应式状态 ──
const inputText = ref('')
const selectedFiles = ref([])
const selectedPreviewUrl = ref('')
const detectionMode = ref('single')
const messageListRef = ref(null)
const fileInputRef = ref(null)
const selectedSessionId = ref(null)
const isDragging = ref(false)
let messageIdSeq = 0

const detectionModes = {
  single: {
    label: '单图检测',
    icon: Picture,
    accept: 'image/*',
    multiple: false,
    placeholder: '描述你的检测需求，或上传一张 PCB 图片...',
  },
  batch: {
    label: '批量 / ZIP',
    icon: FolderOpened,
    accept: 'image/*,.zip',
    multiple: true,
    placeholder: '上传多张图片或 ZIP 压缩包进行批量检测...',
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
  camera: {
    label: '摄像头',
    icon: Camera,
    accept: '',
    multiple: false,
    placeholder: '进入实时摄像头检测工作台...',
  },
}

// ── 计算属性 ──
const currentMode = computed(() => detectionModes[detectionMode.value] || detectionModes.single)

const canSend = computed(() => {
  return !agentStore.isLoading
    && (inputText.value.trim() || selectedFiles.value.length || detectionMode.value === 'camera')
})

const hasUserMessages = computed(() => {
  return agentStore.messages.some((msg) => msg.role === 'user')
})

const fileSummaryTitle = computed(() => {
  if (!selectedFiles.value.length) return ''
  if (['batch', 'folder'].includes(detectionMode.value)) {
    if (detectionMode.value === 'folder') return `${selectedFiles.value.length} 张文件夹图片`
    const hasZip = selectedFiles.value.some((file) => file.name.toLowerCase().endsWith('.zip'))
    return hasZip ? selectedFiles.value[0].name : `${selectedFiles.value.length} 个文件`
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
    return file.type.startsWith('image/') || lowerName.endsWith('.zip')
  }
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
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function handleUsePrompt(prompt) {
  inputText.value = prompt
}

/** 滚动到底部 */
function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
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
  scrollToBottom()

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
      loadSessions()
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

  if (detectionMode.value === 'camera') {
    router.push('/detection')
    return
  }

  const message = inputText.value.trim()
  const filesToSend = [...selectedFiles.value]

  if (filesToSend.length && (!message || detectionMode.value !== 'single')) {
    inputText.value = ''
    clearSelectedFiles()
    if (detectionMode.value === 'single') {
      await runSingleDetection(filesToSend[0])
    } else if (detectionMode.value === 'batch') {
      await runBatchDetection(filesToSend)
    } else if (detectionMode.value === 'folder') {
      await runFolderDetection(filesToSend)
    } else if (detectionMode.value === 'video') {
      await runVideoDetection(filesToSend[0])
    }
    return
  }

  // ── 关键：在清空之前保存文件引用 ──
  const fileToSend = filesToSend[0]
  const imagePreview = fileToSend && fileToSend.type.startsWith('image/')
    ? URL.createObjectURL(fileToSend)
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
  selectedSessionId.value = null
  await loadSessions()
  ElMessage.success('对话已清空')
}

function startNewSession() {
  agentStore.newChat()
  selectedSessionId.value = null
}

async function loadSessions() {
  try {
    const data = await getChatSessions()
    agentStore.sessions = data.items || (data.sessions || []).map((sessionId) => ({
      session_id: sessionId,
      title: `会话 ${sessionId}`,
    }))
  } catch {}
}

async function loadSessionHistory(sessionId) {
  if (!sessionId) return
  try {
    const data = await getChatSessionHistory(sessionId)
    agentStore.currentSessionId = sessionId
    agentStore.messages = (data.messages || []).map((message) => ({
      id: message.id || `history-${messageIdSeq++}`,
      role: message.role === 'ai' ? 'assistant' : message.role,
      content: message.content || '',
      loading: false,
      toolCalls: [],
    }))
    scrollToBottom()
  } catch {}
}

/** 触发文件选择框 */
function triggerFileInput() {
  if (detectionMode.value === 'camera') {
    router.push('/detection')
    return
  }
  fileInputRef.value?.click()
}

function applySelectedFiles(fileList) {
  const files = Array.from(fileList || [])
  if (!files.length) return

  const mode = detectionMode.value
  const normalizedFiles = ['batch', 'folder'].includes(mode) ? files : [files[0]]

  if (mode === 'batch') {
    const zipFiles = normalizedFiles.filter((file) => file.name.toLowerCase().endsWith('.zip'))
    if (zipFiles.length > 1 || (zipFiles.length === 1 && normalizedFiles.length > 1)) {
      ElMessage.warning('ZIP 检测请只选择一个压缩包，或选择多张图片')
      return
    }
  }
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
  if (mode === 'batch') return '批量检测仅支持图片或单个 ZIP 文件'
  if (mode === 'folder') return '文件夹检测仅支持图片文件'
  if (mode === 'video') return '视频检测仅支持 mp4、avi、mov、mkv、wmv、flv'
  return '当前模式不需要上传文件'
}

function selectionMessage(files, mode) {
  if (mode === 'batch') {
    const hasZip = files.some((file) => file.name.toLowerCase().endsWith('.zip'))
    return hasZip ? `${files[0].name} 已选择` : `已选择 ${files.length} 个文件`
  }
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
  if (!agentStore.isLoading) {
    isDragging.value = true
  }
}

/** 拖拽释放文件 */
function handleDrop(event) {
  isDragging.value = false
  if (agentStore.isLoading || detectionMode.value === 'camera') return
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
    imagePreview: URL.createObjectURL(file),
  })

  const assistantMsg = pushMessage({
    role: 'assistant',
    content: '正在检测中...',
    loading: true,
  })
  scrollToBottom()

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
    input.onchange = async (e) => runSingleDetection(e.target.files[0])
    input.click()
  } else if (type === 'batch') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*,.zip'
    input.multiple = true
    input.onchange = async (e) => runBatchDetection(Array.from(e.target.files))
    input.click()
  }
}

async function runBatchDetection(files) {
  if (!files?.length) return

  const isZip = files.some((f) => f.name.toLowerCase().endsWith('.zip'))
  if (isZip && files.length !== 1) {
    ElMessage.warning('ZIP 检测请只选择一个压缩包，或选择多张图片')
    return
  }
  if (files.some((file) => !isValidAttachment(file, 'batch'))) {
    ElMessage.warning(fileTypeWarning('batch'))
    return
  }

  const formData = new FormData()

  if (isZip) {
    formData.append('file', files[0])
    pushMessage({
      role: 'user',
      content: `[快捷检测] ZIP：${files[0].name}`,
    })
  } else {
    files.forEach((f) => formData.append('files', f))
    const imagePreviews = files.map((f) => URL.createObjectURL(f))
    pushMessage({
      role: 'user',
      content: `[快捷检测] ${files.length} 张图片`,
      images: imagePreviews,
    })
  }

  const assistantMsg = pushMessage({
    role: 'assistant',
    content: '正在批量检测中...',
    loading: true,
  })
  scrollToBottom()

  try {
    const apiCall = isZip ? detectZip(formData) : detectBatch(formData)
    const result = await apiCall

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

async function runFolderDetection(files) {
  if (!files?.length) return
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file, file.webkitRelativePath || file.name))
  formData.append('mode', 'folder')
  formData.append('async_mode', 'true')
  pushMessage({ role: 'user', content: `[文件夹检测] ${files.length} 张图片` })
  const assistantMsg = pushMessage({ role: 'assistant', content: '文件夹任务正在提交...', loading: true })
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

/**
 * 视频检测流程：
 * 1. 用户点击 "🎬 视频" 按钮
 * 2. 弹出文件选择框（限制视频格式）
 * 3. 选择视频后，上传到后端
 * 4. 后端返回 task_id，前端开始轮询进度
 * 5. 处理完成后，展示关键帧结果卡片
 */
async function handleVideoDetect() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = detectionModes.video.accept
  input.onchange = async (e) => runVideoDetection(e.target.files[0])
  input.click()
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
  const videoUrl = URL.createObjectURL(file)

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
  scrollToBottom()

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

onMounted(loadSessions)

onBeforeUnmount(() => {
  clearSelectedFiles()
})
</script>

<style lang="scss" scoped>
.chat-page {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  background: transparent;
  overflow: hidden;
}

.chat-page.is-empty {
  justify-content: flex-end;
}

/* ── 消息列表 ── */
.message-list {
  flex: 1;
  width: min(980px, 100%);
  margin: 0 auto;
  overflow-y: auto;
  padding: $spacing-lg $spacing-md $spacing-xl;
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
  background: linear-gradient(135deg, rgba(91, 124, 250, 0.96), rgba(139, 92, 246, 0.9));
  color: #f8fafc;
  border: 1px solid rgba(91, 124, 250, 0.18);
  border-bottom-right-radius: 6px;
}

.assistant-bubble {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(248, 251, 255, 0.68));
  border: 1px solid rgba(226, 232, 240, 0.75);
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

/* ── 输入区域 ── */
.input-area {
  max-width: 980px;
  width: 100%;
  margin: 0 auto;
  padding: $spacing-sm $spacing-md $spacing-md;
  background: transparent;
}

.session-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;

  .el-select { width: 220px; }
}

.input-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: 8px;
  border: 1px solid rgba(203, 213, 225, 0.9);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 251, 255, 0.9));
  box-shadow:
    0 18px 48px rgba(40, 58, 96, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;

  &:focus-within {
    border-color: $border-color-strong;
    background: #fff;
    box-shadow:
      0 0 0 3px rgba(91, 124, 250, 0.1),
      0 20px 54px rgba(91, 124, 250, 0.13);
  }

  &::before {
    content: "";
    position: absolute;
    inset: 1px 12px auto;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(91, 124, 250, 0.24), transparent);
    pointer-events: none;
  }

  .el-textarea {
    flex: 1;
  }

  :deep(.el-textarea__inner) {
    background: transparent;
    box-shadow: none;
    border: 0;
    min-height: 34px !important;
    padding: 7px $spacing-sm;
    color: $text-primary;
    line-height: 1.5;
    scrollbar-width: thin;

    &::placeholder {
      color: $text-placeholder;
    }
  }

  :deep(.el-button) {
    flex-shrink: 0;
  }
}

.attach-btn {
  flex-shrink: 0;
  border-color: transparent;
  background: transparent;
  color: $text-secondary;

  &:hover,
  &:focus {
    background: rgba(139, 92, 246, 0.12);
    color: $primary-color-light;
  }
}

.send-btn {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, $primary-color, $primary-color-light);
  border-color: transparent;
  box-shadow: 0 10px 24px rgba(91, 124, 250, 0.22);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    filter 0.18s ease;

  &:not(.is-disabled):hover,
  &:not(.is-disabled):focus {
    filter: brightness(1.04);
    transform: translateY(-1px);
    box-shadow: 0 14px 30px rgba(91, 124, 250, 0.26);
  }

  &.is-disabled {
    background: rgba(148, 163, 184, 0.22);
    border-color: transparent;
  }
}

.stop-btn {
  height: 34px;
  border-radius: 999px;
}

.clear-chat-btn {
  color: $text-secondary;

  &:hover,
  &:focus {
    color: $danger-color;
    background: rgba(239, 68, 68, 0.1);
  }
}

/* ── 已选文件预览 ── */
.selected-file-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $spacing-sm;
  margin: 0 0 $spacing-sm;
  padding: $spacing-sm;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(248, 251, 255, 0.82));
  border: 1px solid $border-color;
  border-radius: 14px;
  font-size: 13px;
  color: $text-regular;
}

.selected-file-main {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: $spacing-sm;

  img {
    width: 42px;
    height: 42px;
    object-fit: cover;
    border-radius: 10px;
  }
}

.selected-file-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(91, 124, 250, 0.12), rgba(139, 92, 246, 0.1));
  color: $primary-color-light;
  flex-shrink: 0;
}

.selected-file-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;

  strong,
  small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    color: $text-primary;
    font-weight: 600;
  }

  small {
    color: $text-secondary;
  }
}

.remove-file-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: $text-secondary;
  cursor: pointer;

  &:hover,
  &:focus-visible {
    background: rgba(239, 68, 68, 0.1);
    color: $danger-color;
    outline: none;
  }
}

.selected-file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: -2px 0 $spacing-sm;

  span {
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    border-radius: 999px;
    background: rgba(241, 245, 251, 0.9);
    color: $text-secondary;
    font-size: 12px;
    padding: 3px 9px;
  }
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

  .input-row {
    flex-wrap: wrap;
  }

  .input-row :deep(.el-textarea) {
    flex-basis: 100%;
    order: 3;
  }
}
</style>
