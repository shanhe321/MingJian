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

        <div v-if="!running && !connecting" class="viewport-corners" aria-hidden="true">
          <i class="corner top-left"></i><i class="corner top-right"></i>
          <i class="corner bottom-left"></i><i class="corner bottom-right"></i>
        </div>

        <div v-if="!running && !connecting" class="camera-placeholder">
          <span class="scanner-core" aria-hidden="true">
            <i class="orbit orbit-outer"></i>
            <i class="orbit orbit-inner"></i>
            <i class="core-glow"></i>
            <i class="crosshair horizontal"></i>
            <i class="crosshair vertical"></i>
            <i class="scan-line"></i>
            <el-icon><VideoCamera /></el-icon>
          </span>
          <strong>准备开始实时检测</strong>
          <p>连接摄像头后，检测目标和标注画面将在此实时更新。</p>
          <span class="device-readiness"><el-icon><CircleCheck /></el-icon>浏览器摄像头就绪</span>
          <div class="readiness-chips" aria-label="实时检测就绪状态">
            <span><i></i>Camera ready</span>
            <span><i></i>WebSocket ready</span>
            <span>{{ canvasSize.width }} × {{ canvasSize.height }}</span>
          </div>
        </div>

        <div v-else-if="connecting" class="connecting-overlay">
          <el-icon class="is-loading"><Loading /></el-icon>
          <strong>正在建立安全连接</strong>
          <span>请在浏览器中允许摄像头权限</span>
        </div>

        <div v-if="running" class="live-indicator"><i></i>实时推理</div>
        <div v-if="running" class="runtime-hud">
          <span>FPS <strong>{{ Number(stats.fps || 0).toFixed(1) }}</strong></span>
          <span>目标 <strong>{{ stats.objectCount }}</strong></span>
          <span><i></i>已连接</span>
        </div>
      </div>

      <div class="stage-footer">
        <span><el-icon><Monitor /></el-icon>{{ canvasSize.width }} × {{ canvasSize.height }}</span>
        <span><el-icon><Connection /></el-icon>WebSocket 实时通道</span>
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
  CircleCheck,
  Connection,
  Loading,
  Monitor,
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
  box-shadow: 0 20px 48px rgba(42, 62, 101, 0.08);
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.stage-toolbar,
.stage-footer,
.stage-label,
.stage-meta,
.live-indicator,
.device-readiness,
.runtime-hud,
.readiness-chips {
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
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.12em;

  i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #a8b2c2;

    &.active {
      background: $success-color;
      box-shadow: 0 0 0 4px rgba(22, 163, 104, 0.1);
    }
  }
}

.stage-meta {
  gap: 6px;
  color: $text-placeholder;
  font-size: 9px;
}

.preview-frame {
  position: relative;
  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 42%, rgba(91, 124, 250, 0.17), transparent 28%),
    radial-gradient(circle at 22% 78%, rgba(72, 184, 247, 0.1), transparent 30%),
    radial-gradient(circle at 82% 18%, rgba(139, 92, 246, 0.1), transparent 28%),
    linear-gradient(145deg, #f7f9fe 0%, #edf3fb 54%, #f4f1fc 100%);

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba(91, 124, 250, 0.055) 1px, transparent 1px),
      linear-gradient(90deg, rgba(91, 124, 250, 0.05) 1px, transparent 1px);
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
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 104px;
  height: 104px;
  margin-bottom: 20px;
  border-radius: 50%;
  color: $primary-color;
  font-size: 31px;

  .el-icon {
    z-index: 4;
    filter: drop-shadow(0 6px 16px rgba(91, 124, 250, 0.23));
  }

  .orbit,
  .core-glow,
  .crosshair,
  .scan-line {
    position: absolute;
    display: block;
  }

  .orbit {
    border-radius: 50%;
  }

  .orbit-outer {
    inset: -22px;
    border: 1px dashed rgba(91, 124, 250, 0.26);
    animation: orbit-rotate 18s linear infinite;
  }

  .orbit-inner {
    inset: -5px;
    border: 1px solid rgba(72, 184, 247, 0.26);
    box-shadow: inset 0 0 24px rgba(91, 124, 250, 0.08);
    animation: orbit-rotate 13s linear infinite reverse;
  }

  .core-glow {
    inset: 14px;
    border: 1px solid rgba(91, 124, 250, 0.2);
    border-radius: 25px;
    background: rgba(255, 255, 255, 0.72);
    box-shadow:
      0 18px 42px rgba(91, 124, 250, 0.16),
      inset 0 0 22px rgba(139, 92, 246, 0.08);
    animation: core-breathe 3.8s ease-in-out infinite;
  }

  .crosshair.horizontal {
    right: -34px;
    left: -34px;
    top: 50%;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(91, 124, 250, 0.2), transparent);
  }

  .crosshair.vertical {
    top: -34px;
    bottom: -34px;
    left: 50%;
    width: 1px;
    background: linear-gradient(180deg, transparent, rgba(91, 124, 250, 0.2), transparent);
  }

  .scan-line {
    right: 10px;
    left: 10px;
    top: 22px;
    z-index: 3;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(72, 184, 247, 0.8), transparent);
    box-shadow: 0 0 10px rgba(72, 184, 247, 0.36);
    animation: scan-core 3.2s ease-in-out infinite;
  }
}

.camera-placeholder {
  strong { color: $text-primary; font-size: 18px; }
  p { max-width: 430px; margin: 7px 20px 11px; color: $text-secondary; font-size: 12px; line-height: 1.6; }
}

.viewport-corners {
  position: absolute;
  inset: 24px;
  z-index: 1;
  pointer-events: none;
}

.corner {
  position: absolute;
  width: 30px;
  height: 30px;
  border-color: rgba(91, 124, 250, 0.25);
  border-style: solid;

  &.top-left { top: 0; left: 0; border-width: 1px 0 0 1px; }
  &.top-right { top: 0; right: 0; border-width: 1px 1px 0 0; }
  &.bottom-left { bottom: 0; left: 0; border-width: 0 0 1px 1px; }
  &.bottom-right { right: 0; bottom: 0; border-width: 0 1px 1px 0; }
}

.device-readiness {
  gap: 5px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.68);
  color: $success-color;
  font-size: 9px;
}

.readiness-chips {
  position: absolute;
  right: 22px;
  bottom: 18px;
  left: 22px;
  justify-content: center;
  flex-wrap: wrap;
  gap: 7px;

  span {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    height: 25px;
    padding: 0 9px;
    border: 1px solid rgba(190, 203, 224, 0.64);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.58);
    color: $text-secondary;
    font-size: 9px;
    backdrop-filter: blur(8px);

    i {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: $success-color;
    }
  }
}

.connecting-overlay {
  background: rgba(242, 246, 252, 0.82);
  backdrop-filter: blur(8px);

  .el-icon { color: $primary-color; font-size: 28px; }
  strong { margin-top: 10px; color: $text-primary; font-size: 14px; }
  span { margin-top: 4px; color: $text-secondary; font-size: 10px; }
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
  font-size: 9px;
  backdrop-filter: blur(12px);

  i { width: 6px; height: 6px; border-radius: 50%; background: #50e3a4; }
}

.runtime-hud {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 3;
  gap: 6px;

  span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 27px;
    padding: 0 8px;
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 999px;
    background: rgba(20, 29, 46, 0.56);
    color: rgba(255, 255, 255, 0.78);
    font-size: 9px;
    backdrop-filter: blur(12px);

    strong { color: #fff; }
    i { width: 5px; height: 5px; border-radius: 50%; background: #50e3a4; }
  }
}

.stage-footer {
  height: 32px;
  flex: 0 0 32px;
  gap: 18px;
  padding: 0 16px;
  color: $text-placeholder;
  font-size: 9px;

  span { display: inline-flex; align-items: center; gap: 5px; }
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
  box-shadow: 0 16px 38px rgba(42, 62, 101, 0.07);
  box-sizing: border-box;
}

@keyframes orbit-rotate {
  to { transform: rotate(360deg); }
}

@keyframes core-breathe {
  0%, 100% { transform: scale(0.97); opacity: 0.72; }
  50% { transform: scale(1.03); opacity: 1; }
}

@keyframes scan-core {
  0%, 100% { transform: translateY(0); opacity: 0.25; }
  50% { transform: translateY(58px); opacity: 0.9; }
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
  .runtime-hud span:nth-child(3) { display: none; }
  .readiness-chips { bottom: 12px; }
}

@media (prefers-reduced-motion: reduce) {
  .orbit,
  .core-glow,
  .scan-line {
    animation: none !important;
  }
}
</style>
