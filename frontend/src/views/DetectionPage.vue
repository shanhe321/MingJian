<template>
  <div class="detection-page">
    <!-- ── 页面标题 ── -->
    <div class="page-header">
      <h2>摄像头实时检测</h2>
      <el-tag :type="statusTagType" size="large">
        {{ statusText }}
      </el-tag>
    </div>

    <!-- ── 主体区域 ── -->
    <div class="main-content">
      <!-- 左侧：视频预览 -->
      <div class="preview-panel">
        <div class="video-wrapper">
          <!-- 原始视频（隐藏，用于获取帧） -->
          <video
            ref="videoRef"
            autoplay
            playsinline
            muted
            style="display: none"
          ></video>

          <!-- 标注画面 Canvas（显示标注后的帧） -->
          <canvas
            ref="canvasRef"
            class="preview-canvas"
            :width="canvasWidth"
            :height="canvasHeight"
          ></canvas>

          <!-- 未开启时的占位 -->
          <div v-if="!isRunning" class="placeholder">
            <p>点击下方按钮开启摄像头</p>
          </div>
        </div>

        <!-- FPS 和帧数信息 -->
        <div v-if="isRunning" class="video-stats">
          <el-tag type="success">FPS: {{ currentFps }}</el-tag>
          <el-tag type="info">帧: {{ frameCount }}</el-tag>
          <el-tag type="info">推理: {{ inferenceTime }}ms</el-tag>
        </div>
      </div>

      <!-- 右侧：检测结果 -->
      <div class="result-panel">
        <section class="control-panel" aria-label="实时检测控制">
          <div class="panel-section status-section">
            <div class="section-title">检测状态</div>
            <div
              class="status-inline"
              :class="{
                'is-running': isRunning,
                'is-connecting': isConnecting,
                'is-error': connectionError,
              }"
            >
              <span class="status-dot"></span>
              <span>{{ statusText }}</span>
            </div>
            <p v-if="connectionError" class="status-error">{{ connectionError }}</p>
          </div>

          <div class="panel-section camera-control-section">
            <div class="section-title">摄像头控制</div>
            <button
              v-if="!isRunning"
              type="button"
              class="camera-action-btn"
              :class="{ 'is-loading': isConnecting }"
              :disabled="isConnecting"
              @click="startCamera"
            >
              <span class="action-dot"></span>
              {{ isConnecting ? '正在连接摄像头' : '开启摄像头' }}
            </button>
            <button
              v-else
              type="button"
              class="camera-action-btn is-stop"
              @click="stopCamera()"
            >
              <span class="action-dot"></span>
              停止摄像头
            </button>
          </div>

          <div class="panel-section inference-section">
            <div class="section-title">推理配置</div>
            <label class="field-label" for="detect-mode-select">推理设备</label>
            <el-select
              id="detect-mode-select"
              v-model="detectMode"
              class="device-select"
              :disabled="isRunning"
              popper-class="rsod-dark-popper device-select-popper"
            >
              <el-option value="cpu" label="CPU 节能">
                <div class="device-option">
                  <strong>CPU 节能</strong>
                  <small>适合本机开发，帧率较低</small>
                </div>
              </el-option>
              <el-option value="gpu" label="GPU 加速">
                <div class="device-option">
                  <strong>GPU 加速</strong>
                  <small>适合支持 CUDA 的环境</small>
                </div>
              </el-option>
            </el-select>

            <div class="confidence-head">
              <span class="field-label">置信度</span>
              <span class="confidence-value">{{ confThreshold.toFixed(2) }}</span>
            </div>
            <el-slider
              v-model="confThreshold"
              class="confidence-slider"
              :min="0.1"
              :max="0.9"
              :step="0.05"
              :disabled="isRunning"
              :show-tooltip="true"
              :format-tooltip="formatConfidenceTooltip"
            />
          </div>
        </section>

        <el-card class="stats-card" shadow="never">
          <template #header>
            <span>实时检测统计</span>
          </template>

          <div class="stats-grid">
            <div class="stat-item">
              <div class="stat-value">{{ objectCount }}</div>
              <div class="stat-label">当前目标数</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ currentFps }}</div>
              <div class="stat-label">实时 FPS</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ inferenceTime }}</div>
              <div class="stat-label">推理耗时(ms)</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ frameCount }}</div>
              <div class="stat-label">已处理帧</div>
            </div>
          </div>
        </el-card>

        <el-card class="detections-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span>当前帧目标列表</span>
              <el-tag size="small"
                >{{ currentDetections.length }} 个目标</el-tag
              >
            </div>
          </template>

          <div v-if="currentDetections.length === 0" class="empty-state">
            暂无检测目标
          </div>

          <div v-else class="detection-list">
            <div
              v-for="(det, index) in currentDetections"
              :key="index"
              class="detection-item"
            >
              <div class="det-info">
                <span class="det-class">{{ det.class_name }}</span>
                <el-progress
                  :percentage="Math.round(det.confidence * 100)"
                  :stroke-width="6"
                  :show-text="true"
                  style="width: 120px"
                />
              </div>
              <div class="det-bbox">
                [{{ det.bbox.map((v) => Math.round(v)).join(", ") }}]
              </div>
            </div>
          </div>
        </el-card>

        <!-- 类别分布统计 -->
        <el-card
          v-if="Object.keys(classDistribution).length > 0"
          class="distribution-card"
          shadow="never"
        >
          <template #header>
            <span>类别分布</span>
          </template>
          <div class="distribution-list">
            <div
              v-for="(count, className) in classDistribution"
              :key="className"
              class="distribution-item"
            >
              <span class="class-name">{{ className }}</span>
              <el-tag size="small" type="primary">{{ count }}</el-tag>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <!-- ── 控制栏 ── -->
    <div class="control-bar">
      <el-button
        v-if="!isRunning"
        type="primary"
        size="large"
        @click="startCamera"
        :loading="isConnecting"
      >
        开启摄像头
      </el-button>
      <el-button v-else type="danger" size="large" @click="stopCamera()">
        停止检测
      </el-button>

      <el-divider direction="vertical" />

      <!-- GPU/CPU 模式选择 -->
      <span class="control-label">推理模式：</span>
      <el-radio-group v-model="detectMode" :disabled="isRunning">
        <el-radio-button value="cpu">CPU 节能</el-radio-button>
        <el-radio-button value="gpu">GPU 加速</el-radio-button>
      </el-radio-group>

      <el-divider direction="vertical" />

      <!-- 置信度阈值 -->
      <span class="control-label">置信度：</span>
      <el-slider
        v-model="confThreshold"
        :min="0.1"
        :max="0.9"
        :step="0.05"
        :disabled="isRunning"
        style="width: 150px"
        show-input
      />
    </div>
  </div>
</template>

<script setup>
/**
 * DetectionPage.vue — 摄像头实时检测独立页面
 *
 * 功能：
 *   - 浏览器 getUserMedia() 获取摄像头画面
 *   - WebSocket 实时发送帧数据到后端（使用 cameraWs.js 工具）
 *   - 接收后端返回的标注帧并渲染到 Canvas
 *   - GPU/CPU 双模式切换
 *   - 实时统计：FPS、目标数、推理耗时、类别分布
 */
import { createCameraWs } from '@/utils/cameraWs'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, ref } from 'vue'

// ── 响应式状态 ──
const videoRef = ref(null)
const canvasRef = ref(null)

// 摄像头状态
const isRunning = ref(false)
const isConnecting = ref(false)
const connectionError = ref('')

// 检测配置
const detectMode = ref('cpu')
const confThreshold = ref(0.25)

// 实时统计
const currentFps = ref(0)
const frameCount = ref(0)
const inferenceTime = ref(0)
const objectCount = ref(0)
const currentDetections = ref([])

// Canvas 尺寸
const canvasWidth = ref(640)
const canvasHeight = ref(480)

// ── WebSocket 实例 ──
let cameraWs = null
let mediaStream = null
const userStore = useUserStore()

// ── 计算属性 ──
const statusText = computed(() => {
  if (connectionError.value) return '发生错误'
  if (isConnecting.value) return '连接中...'
  if (isRunning.value) return '运行中'
  return '未启动'
})

const statusTagType = computed(() => {
  if (isConnecting.value) return 'warning'
  if (isRunning.value) return 'success'
  return 'info'
})

const classDistribution = computed(() => {
  const dist = {}
  for (const det of currentDetections.value) {
    dist[det.class_name] = (dist[det.class_name] || 0) + 1
  }
  return dist
})

function formatConfidenceTooltip(value) {
  return value.toFixed(2)
}

/** 开启摄像头 */
async function startCamera() {
  try {
    connectionError.value = ''
    isConnecting.value = true

    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      throw new Error('云端摄像头必须通过 HTTPS 页面访问，请检查站点证书')
    }

    // 1. 获取摄像头权限
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        facingMode: { ideal: 'environment' },
      },
      audio: false,
    })

    // 2. 将媒体流绑定到隐藏的 video 元素
    videoRef.value.srcObject = mediaStream
    await videoRef.value.play()

    // 3. 更新 Canvas 尺寸
    canvasWidth.value = videoRef.value.videoWidth || 640
    canvasHeight.value = videoRef.value.videoHeight || 480

    // 4. 创建并连接 WebSocket
    createCameraWsInstance()
    cameraWs.connect()

    isRunning.value = true
    ElMessage.success('摄像头已开启')
  } catch (err) {
    connectionError.value = err.message || '摄像头开启失败'
    console.error('[摄像头开启失败]', err)
    ElMessage.error(`摄像头开启失败: ${err.message}`)
    isConnecting.value = false
  }
}

/** 创建 WebSocket 实例 */
function createCameraWsInstance() {
  cameraWs = createCameraWs({
    mode: detectMode.value,
    conf: confThreshold.value,
    token: userStore.token,
    onResult: handleDetectionResult,
    onConfigOk: handleConfigOk,
    onError: handleWsError,
    onClose: handleWsClose,
  })
}

/** 处理检测结果 */
function handleDetectionResult(data) {
  renderAnnotatedFrame(data.annotatedFrame)
  currentFps.value = data.fps
  frameCount.value = data.frameCount
  inferenceTime.value = data.inferenceTime
  objectCount.value = data.objectCount
  currentDetections.value = data.detections
}

/** 处理配置成功 */
function handleConfigOk() {
  isConnecting.value = false
  connectionError.value = ''
  requestAnimationFrame(sendSingleFrame)
}

/** 处理错误 */
function handleWsError(message) {
  connectionError.value = message || '检测连接异常'
  ElMessage.error(message)
  isConnecting.value = false
  isRunning.value = false
  releaseMediaStream()
}

/** 处理连接关闭 */
function handleWsClose() {
  isConnecting.value = false
  if (isRunning.value) {
    isRunning.value = false
    releaseMediaStream()
  }
}

function releaseMediaStream() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop())
    mediaStream = null
  }
  if (videoRef.value) videoRef.value.srcObject = null
}

/** 发送单帧 */
function sendSingleFrame() {
  if (!cameraWs || !cameraWs.isConnected) return
  if (!videoRef.value || videoRef.value.readyState < 2) return

  const targetSize = detectMode.value === 'cpu' ? 416 : 640
  const tempCanvas = document.createElement('canvas')
  tempCanvas.width = targetSize
  tempCanvas.height = targetSize
  const ctx = tempCanvas.getContext('2d')

  const vw = videoRef.value.videoWidth
  const vh = videoRef.value.videoHeight
  const scale = Math.min(targetSize / vw, targetSize / vh)
  const x = (targetSize - vw * scale) / 2
  const y = (targetSize - vh * scale) / 2
  ctx.drawImage(videoRef.value, x, y, vw * scale, vh * scale)

  const dataUrl = tempCanvas.toDataURL('image/jpeg', 0.6)
  const base64Data = dataUrl.split(',')[1]

  cameraWs.sendFrame(base64Data)
}

/** 渲染标注帧到 Canvas */
function renderAnnotatedFrame(annotatedBase64) {
  if (!canvasRef.value) return

  const img = new Image()
  img.onload = () => {
    const ctx = canvasRef.value.getContext('2d')
    canvasRef.value.width = img.width
    canvasRef.value.height = img.height
    ctx.drawImage(img, 0, 0)

    requestAnimationFrame(sendSingleFrame)
  }
  img.src = `data:image/jpeg;base64,${annotatedBase64}`
}

/** 停止摄像头 */
function stopCamera(notify = true) {
  const wasActive = isRunning.value || isConnecting.value || Boolean(mediaStream)
  // 关闭 WebSocket
  if (cameraWs) {
    cameraWs.close()
    cameraWs = null
  }

  // 停止摄像头
  releaseMediaStream()

  // 重置状态
  isRunning.value = false
  isConnecting.value = false
  connectionError.value = ''
  currentFps.value = 0
  inferenceTime.value = 0
  objectCount.value = 0
  currentDetections.value = []

  // 清空 Canvas
  if (canvasRef.value) {
    const ctx = canvasRef.value.getContext('2d')
    ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)
  }

  if (notify && wasActive) ElMessage.info('摄像头已停止')
}

// ── 组件销毁时清理 ──
onBeforeUnmount(() => {
  stopCamera(false)
})
</script>

<style lang="scss" scoped>
.detection-page {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - #{$header-height} - 48px);
  color: $text-regular;
  background: transparent;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: min(1440px, 100%);
  margin: 0 auto $spacing-lg;

  h2 {
    margin: 0;
    color: $text-primary;
    font-size: 24px;
    font-weight: 650;
    line-height: 1.25;
  }

  :deep(.el-tag) {
    display: none;
  }
}

.main-content {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
  gap: $spacing-lg;
  flex: 1;
  width: min(1440px, 100%);
  margin: 0 auto;
  min-height: 0;
  align-items: stretch;
}

/* 左侧预览区 */
.preview-panel {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
  min-width: 0;
}

.video-wrapper {
  position: relative;
  aspect-ratio: 16 / 9;
  min-height: 0;
  border: 1px solid rgba(203, 213, 225, 0.78);
  border-radius: $border-radius-lg;
  background:
    radial-gradient(circle at 50% 24%, rgba(91, 124, 250, 0.18), transparent 24rem),
    radial-gradient(circle at 44% 48%, rgba(139, 92, 246, 0.12), transparent 18rem),
    linear-gradient(145deg, #090d13 0%, #111720 100%);
  box-shadow:
    0 24px 60px rgba(40, 58, 96, 0.12),
    inset 0 0 0 1px rgba(255, 255, 255, 0.04);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;

  &::before {
    content: "";
    position: absolute;
    inset: 12px;
    border-radius: calc(#{$border-radius-lg} - 4px);
    border: 1px solid rgba(91, 124, 250, 0.12);
    pointer-events: none;
    z-index: 1;
  }
}

.preview-canvas {
  width: 100%;
  max-height: 100%;
  height: auto;
  display: block;
  object-fit: contain;
}

.placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $spacing-sm;
  color: $text-secondary;
  text-align: center;
  pointer-events: none;

  &::before {
    content: "";
    width: 54px;
    height: 54px;
    border: 1px solid rgba(167, 139, 250, 0.28);
    border-radius: 18px;
    background: rgba(139, 92, 246, 0.12);
    box-shadow: 0 0 34px rgba(139, 92, 246, 0.12);
  }

  p {
    margin: 0;
    font-size: 0;
    color: $text-regular;

    &::before {
      content: "摄像头尚未启动";
      display: block;
      color: $text-primary;
      font-size: 16px;
      font-weight: 600;
      line-height: 1.6;
    }

    &::after {
      content: "在右侧控制面板中开启摄像头";
      display: block;
      color: $text-secondary;
      font-size: 13px;
      line-height: 1.6;
    }
  }
}

.video-stats {
  display: none;
}

/* 右侧结果区 */
.result-panel {
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
  min-width: 0;
  max-height: calc(100vh - #{$header-height} - 96px);
  overflow: hidden;
}

.control-panel {
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
  padding: $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 251, 255, 0.86));
  box-shadow:
    $shadow-sm,
    inset 0 1px 0 rgba(255, 255, 255, 0.95);
}

.panel-section {
  padding-bottom: $spacing-sm;
  border-bottom: 1px solid $border-color;

  &:last-child {
    padding-bottom: 0;
    border-bottom: 0;
  }
}

.section-title {
  margin-bottom: $spacing-sm;
  color: $text-primary;
  font-size: 13px;
  font-weight: 650;
}

.status-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: $text-secondary;
  font-size: 13px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: $text-placeholder;
  box-shadow: 0 0 0 4px rgba(107, 114, 128, 0.12);
}

.status-inline.is-connecting .status-dot {
  background: $primary-color-light;
  box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.16);
  animation: status-pulse 1.25s ease-in-out infinite;
}

.status-inline.is-running .status-dot {
  background: $success-color;
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.14);
}

.status-inline.is-error .status-dot {
  background: $danger-color;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.14);
}

.status-error {
  margin: $spacing-xs 0 0;
  color: $danger-color;
  font-size: 12px;
  line-height: 1.5;
}

.camera-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 40px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.86), rgba(241, 245, 251, 0.76));
  color: $text-primary;
  cursor: pointer;
  font-weight: 600;
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
    box-shadow: 0 10px 24px rgba(91, 124, 250, 0.1);
    outline: none;

    .action-dot {
      background: $primary-color-light;
    }
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.72;
  }

  &.is-stop {
    border-color: rgba(220, 90, 90, 0.24);
    background: rgba(254, 242, 242, 0.9);
    color: $danger-color;

    .action-dot {
      background: $danger-color;
    }

    &:hover,
    &:focus-visible {
      border-color: rgba(248, 113, 113, 0.42);
      background: rgba(254, 226, 226, 0.92);
    }
  }
}

.action-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: $text-secondary;
}

.field-label {
  display: inline-flex;
  margin-bottom: 6px;
  color: $text-secondary;
  font-size: 12px;
}

.device-select {
  width: 100%;
  margin-bottom: $spacing-sm;
}

.device-option {
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong {
    color: $text-primary;
    font-size: 13px;
  }

  small {
    color: $text-secondary;
    font-size: 12px;
  }
}

.confidence-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: $spacing-xs;
}

.confidence-value {
  color: $primary-color-light;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.confidence-slider {
  margin: 0 4px;
}

@keyframes status-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }

  50% {
    transform: scale(1.35);
    opacity: 0.7;
  }
}

.stats-card,
.detections-card,
.distribution-card {
  --el-card-bg-color: rgba(255, 255, 255, 0.9);
  border-color: #{$border-color};
  border-radius: $border-radius-lg;
  box-shadow:
    $shadow-sm,
    inset 0 1px 0 rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);

  :deep(.el-card__header) {
    padding: 12px 14px;
    color: $text-primary;
    font-size: 14px;
    font-weight: 600;
    border-bottom-color: $border-color;
  }

  :deep(.el-card__body) {
    padding: 14px;
  }
}

.detections-card {
  flex: 1;
  min-height: 0;

  :deep(.el-card__body) {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $spacing-sm;
}

.stat-item {
  min-height: 66px;
  padding: 10px 12px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: $border-radius-md;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(241, 245, 251, 0.78));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.stat-value {
  color: $primary-color-dark;
  font-size: 23px;
  font-weight: 700;
  line-height: 1.1;
}

.stat-label {
  font-size: 12px;
  color: $text-secondary;
  margin-top: 5px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.empty-state {
  text-align: center;
  color: $text-secondary;
  padding: 28px $spacing-md;
}

.detection-list {
  flex: 1;
  min-height: 0;
  max-height: none;
  overflow-y: auto;
}

.detection-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $spacing-sm;
  padding: 12px 0;
  border-bottom: 1px solid $border-color;

  &:last-child {
    border-bottom: none;
  }
}

.det-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.det-class {
  font-weight: 600;
  min-width: 80px;
  color: $text-primary;
}

.det-bbox {
  font-size: 12px;
  color: $text-placeholder;
  font-family: monospace;
  line-height: 1.7;
  text-align: right;
}

.distribution-list {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-sm;
}

.distribution-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: 6px 10px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
}

.class-name {
  font-weight: 500;
  color: $text-regular;
}

/* 控制栏 */
.control-bar {
  display: none;
  align-items: center;
  flex-wrap: wrap;
  gap: $spacing-md;
  padding: $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
}

.control-bar :deep(.el-divider--vertical) {
  border-left-color: $border-color;
}

.control-bar :deep(.el-radio-button__inner) {
  background: $surface-color-soft;
  border-color: $border-color;
  color: $text-secondary;
}

.control-bar :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: rgba(91, 124, 250, 0.12);
  border-color: rgba(91, 124, 250, 0.28);
  color: $text-primary;
  box-shadow: -1px 0 0 0 rgba(91, 124, 250, 0.28);
}

.control-bar :deep(.el-slider) {
  --el-slider-main-bg-color: #{$primary-color};
  --el-slider-runway-bg-color: rgba(148, 163, 184, 0.18);
}

.control-bar :deep(.el-slider__input) {
  width: 92px;
}

.control-label {
  font-size: 14px;
  color: $text-secondary;
  white-space: nowrap;
}

@media (max-width: 1180px) {
  .main-content {
    grid-template-columns: 1fr;
  }

  .result-panel {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .distribution-card {
    grid-column: 1 / -1;
  }
}

@media (max-width: 760px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
    gap: $spacing-sm;
  }

  .video-wrapper {
    min-height: 300px;
  }

  .result-panel {
    display: flex;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .control-bar {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
