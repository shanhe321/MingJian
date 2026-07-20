<template>
  <section class="camera-workspace">
    <main class="camera-stage">
      <div class="stage-toolbar">
        <span class="stage-label"><i :class="{ active: cameraReady }"></i>{{ running ? 'LIVE' : cameraReady ? 'CAMERA CONNECTED' : 'CAMERA PREVIEW' }}</span>
        <span v-if="running" class="stage-meta">{{ device.toUpperCase() }} · {{ activeSceneName }}</span>
      </div>

      <div class="preview-frame" :class="{ 'is-running': running || connecting }">
        <video ref="videoRef" autoplay playsinline muted></video>
        <canvas
          v-show="hasAnnotatedFrame"
          ref="canvasRef"
          :width="canvasSize.width"
          :height="canvasSize.height"
        ></canvas>

        <div v-if="!running && !connecting" class="camera-placeholder">
          <span class="scanner-core" aria-hidden="true">
            <el-icon><VideoCamera /></el-icon>
          </span>
          <strong>准备开始实时检测</strong>
          <p>启动后将在此显示实时检测画面。</p>
        </div>

        <div v-else-if="connecting" class="connecting-overlay">
          <el-icon class="is-loading"><Loading /></el-icon>
          <strong>正在建立安全连接</strong>
          <span>请在浏览器中允许摄像头权限</span>
        </div>

        <div v-if="running" class="live-indicator"><i></i>实时推理</div>
      </div>
    </main>

    <aside class="workspace-sidebar">
      <CameraControlPanel
        :scenes="scenes"
        :scene-id="sceneId"
        :device="device"
        :confidence="confidence"
        :iou="iou"
        :running="running"
        :connecting="connecting"
        :error="error"
        :camera-ready="cameraReady"
        :inference-connected="inferenceConnected"
        @update:scene-id="sceneId = $event"
        @update:device="device = $event"
        @update:confidence="confidence = $event"
        @update:iou="iou = $event"
        @start="start"
        @stop="stop()"
      />

      <DetectionStatsPanel
        :fps="stats.fps"
        :object-count="stats.objectCount"
        :frame-count="stats.frameCount"
        :inference-time="stats.inferenceTime"
      />

      <FrameTargetsPanel :detections="stats.detections" />
    </aside>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Loading,
  VideoCamera,
} from '@element-plus/icons-vue'
import { getScenes } from '@/api/scenes'
import { useUserStore } from '@/stores/user'
import { createCameraWs } from '@/utils/cameraWs'
import {
  cameraAccessErrorMessage,
  createCameraRuntimeState,
  nextCameraRuntimeState,
  releaseCameraResources,
} from '@/utils/cameraRuntime'
import CameraControlPanel from './CameraControlPanel.vue'
import DetectionStatsPanel from './DetectionStatsPanel.vue'
import FrameTargetsPanel from './FrameTargetsPanel.vue'

const userStore = useUserStore()
const videoRef = ref(null)
const canvasRef = ref(null)
const scenes = ref([])
const sceneId = ref(null)
const device = ref('cpu')
const confidence = ref(0.25)
const iou = ref(0.45)
const runtime = reactive(createCameraRuntimeState())
const cameraReady = computed(() => runtime.camera === 'connected')
const inferenceConnected = computed(() => runtime.inference === 'connected')
const running = inferenceConnected
const connecting = computed(() => runtime.camera === 'requesting' || runtime.inference === 'connecting')
const error = computed(() => runtime.error)
const hasAnnotatedFrame = ref(false)
const canvasSize = reactive({ width: 960, height: 540 })
const stats = reactive({
  fps: 0,
  inferenceTime: 0,
  frameCount: 0,
  objectCount: 0,
  detections: [],
})

let mediaStream = null
let client = null
let stopping = false
let animationFrameId = null
let activeRunId = 0

const activeSceneName = computed(() => {
  const scene = scenes.value.find((item) => item.id === sceneId.value)
  return scene?.display_name || scene?.name || '默认场景'
})

function resetStats() {
  Object.assign(stats, { fps: 0, inferenceTime: 0, frameCount: 0, objectCount: 0, detections: [] })
  hasAnnotatedFrame.value = false
  canvasRef.value?.getContext('2d')?.clearRect(0, 0, canvasSize.width, canvasSize.height)
}

function transitionRuntime(event, message = '') {
  Object.assign(runtime, nextCameraRuntimeState(runtime, event, message))
}

async function start() {
  if (running.value || connecting.value) return
  stopping = false
  const runId = ++activeRunId
  transitionRuntime('start')
  resetStats()

  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器或安全上下文不支持摄像头')
    }

    const acquiredStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: { ideal: 'environment' },
      },
      audio: false,
    })
    if (runId !== activeRunId) {
      releaseCameraResources({ mediaStream: acquiredStream })
      return
    }
    mediaStream = acquiredStream
    videoRef.value.srcObject = mediaStream
    await videoRef.value.play()
    if (runId !== activeRunId) {
      releaseResources()
      return
    }
    canvasSize.width = videoRef.value.videoWidth || 960
    canvasSize.height = videoRef.value.videoHeight || 540
    transitionRuntime('camera_ready')

    client = createCameraWs({
      mode: device.value,
      conf: confidence.value,
      iou: iou.value,
      sceneId: sceneId.value,
      token: userStore.token,
      onConfigOk: () => {
        if (runId !== activeRunId) return
        transitionRuntime('inference_ready')
        sendFrame()
      },
      onResult: (result) => {
        if (runId === activeRunId) handleResult(result, runId)
      },
      onError: (message) => {
        if (runId === activeRunId) handleError(message)
      },
      onClose: () => {
        if (runId === activeRunId) handleClose()
      },
    })
    client.connect()
  } catch (startError) {
    if (runId !== activeRunId) return
    handleError(cameraAccessErrorMessage(startError))
  }
}

function sendFrame() {
  if (!running.value || !client?.isConnected || !videoRef.value) return
  const target = device.value === 'cpu' ? 416 : 640
  const buffer = document.createElement('canvas')
  buffer.width = target
  buffer.height = target
  const context = buffer.getContext('2d')
  const videoWidth = videoRef.value.videoWidth
  const videoHeight = videoRef.value.videoHeight
  if (!context || !videoWidth || !videoHeight) return

  const scale = Math.min(target / videoWidth, target / videoHeight)
  context.drawImage(
    videoRef.value,
    (target - videoWidth * scale) / 2,
    (target - videoHeight * scale) / 2,
    videoWidth * scale,
    videoHeight * scale,
  )
  client.sendFrame(buffer.toDataURL('image/jpeg', 0.6).split(',')[1])
}

function handleResult(result, resultRunId = activeRunId) {
  if (!running.value || resultRunId !== activeRunId) return
  Object.assign(stats, {
    fps: result.fps,
    inferenceTime: result.inferenceTime,
    frameCount: result.frameCount,
    objectCount: result.objectCount,
    detections: result.detections,
  })

  const image = new Image()
  image.onload = () => {
    if (!running.value || resultRunId !== activeRunId) return
    const context = canvasRef.value?.getContext('2d')
    context?.clearRect(0, 0, canvasSize.width, canvasSize.height)
    context?.drawImage(image, 0, 0, canvasSize.width, canvasSize.height)
    hasAnnotatedFrame.value = true
    scheduleNextFrame(resultRunId)
  }
  image.onerror = () => scheduleNextFrame(resultRunId)
  image.src = `data:image/jpeg;base64,${result.annotatedFrame}`
}

function scheduleNextFrame(runId) {
  if (!running.value || runId !== activeRunId) return
  animationFrameId = requestAnimationFrame(() => {
    animationFrameId = null
    if (running.value && runId === activeRunId) sendFrame()
  })
}

function releaseResources({ closeSocket = true } = {}) {
  releaseCameraResources({
    mediaStream,
    client: closeSocket ? client : null,
    animationFrameId,
  })
  animationFrameId = null
  mediaStream = null
  if (closeSocket) client = null
  if (videoRef.value) videoRef.value.srcObject = null
}

function handleError(message) {
  stopping = true
  activeRunId += 1
  transitionRuntime('failed', message)
  releaseResources()
  resetStats()
}

function handleClose() {
  if (stopping) {
    releaseResources({ closeSocket: false })
    client = null
    resetStats()
    return
  }
  const unexpected = !stopping && (running.value || connecting.value || cameraReady.value)
  activeRunId += 1
  transitionRuntime(unexpected ? 'failed' : 'stop', unexpected ? '摄像头推理通道已断开，请重新启动' : '')
  releaseResources({ closeSocket: false })
  client = null
  resetStats()
}

function stop(notify = true) {
  if (!running.value && !connecting.value && !cameraReady.value && !client && !mediaStream) return
  stopping = true
  activeRunId += 1
  transitionRuntime('stop')
  releaseResources()
  resetStats()
  if (notify) ElMessage.success('实时检测已停止')
}

onMounted(async () => {
  try {
    const data = await getScenes()
    scenes.value = data.items || data || []
    sceneId.value = scenes.value[0]?.id ?? null
  } catch {
    scenes.value = []
  }
})

onBeforeUnmount(() => stop(false))
</script>

<style lang="scss" scoped>
.camera-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  box-sizing: border-box;
}

.camera-stage {
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(199, 210, 228, 0.78);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 5px 16px rgba(37, 99, 235, 0.04);
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.stage-toolbar,
.stage-label,
.stage-meta,
.live-indicator {
  display: flex;
  align-items: center;
}

.stage-toolbar {
  height: 40px;
  flex: 0 0 40px;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.74);
}

.stage-label {
  gap: 7px;
  color: $text-secondary;
  font-size: 13px;
  font-weight: 750;
  letter-spacing: 0.12em;

  i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #a8b2c2;

    &.active {
      background: $success-color;
    }
  }
}

.stage-meta {
  gap: 6px;
  color: $text-placeholder;
  font-size: 13px;
}

.preview-frame {
  position: relative;
  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow: hidden;
  background: #f5faff;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba(59, 130, 246, 0.045) 1px, transparent 1px),
      linear-gradient(90deg, rgba(56, 189, 248, 0.04) 1px, transparent 1px);
    background-size: 30px 30px;
    pointer-events: none;
    transition: opacity 0.25s ease;
  }

  video,
  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  video { opacity: 0; transition: opacity 0.25s ease; }
  &.is-running video { opacity: 1; }
  &.is-running::before { opacity: 0.12; }
  canvas { z-index: 1; }
}

.camera-placeholder,
.connecting-overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.scanner-core {
  display: inline-grid;
  place-items: center;
  width: 68px;
  height: 68px;
  margin-bottom: 16px;
  border: 1px solid rgba(59, 130, 246, 0.18);
  border-radius: 20px;
  background: #eef7ff;
  color: $primary-color;
  font-size: 28px;
}

.camera-placeholder {
  strong { color: $text-primary; font-size: 18px; }
  p { max-width: 430px; margin: 7px 20px 0; color: $text-secondary; font-size: 13px; line-height: 1.6; }
}

.connecting-overlay {
  background: #f5faff;

  .el-icon { color: $primary-color; font-size: 28px; }
  strong { margin-top: 10px; color: $text-primary; font-size: 14px; }
  span { margin-top: 4px; color: $text-secondary; font-size: 13px; }
}

.live-indicator {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 3;
  gap: 6px;
  height: 27px;
  padding: 0 9px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 999px;
  background: rgba(20, 29, 46, 0.62);
  color: #fff;
  font-size: 13px;

  i { width: 6px; height: 6px; border-radius: 50%; background: #50e3a4; }
}

.workspace-sidebar {
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(199, 210, 228, 0.76);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 5px 16px rgba(37, 99, 235, 0.035);
  box-sizing: border-box;
}

@media (max-width: 1100px) {
  .camera-workspace {
    height: auto;
    grid-template-columns: 1fr;
    overflow: visible;
  }

  .camera-stage { height: min(560px, calc(100vh - #{$header-height} - 110px)); min-height: 440px; }
  .workspace-sidebar { height: 610px; }
}

@media (max-width: 720px) {
  .camera-stage { height: 440px; min-height: 440px; }
  .workspace-sidebar { height: 650px; }
}
</style>
