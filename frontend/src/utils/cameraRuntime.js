export function createCameraRuntimeState() {
  return { camera: 'idle', inference: 'idle', error: '' }
}

export function nextCameraRuntimeState(state, event, message = '') {
  switch (event) {
    case 'start':
      return { camera: 'requesting', inference: 'idle', error: '' }
    case 'camera_ready':
      return { camera: 'connected', inference: 'connecting', error: '' }
    case 'inference_ready':
      return { camera: 'connected', inference: 'connected', error: '' }
    case 'failed':
      return { camera: 'idle', inference: 'idle', error: message }
    case 'stop':
      return createCameraRuntimeState()
    default:
      return { ...state }
  }
}

export function cameraAccessErrorMessage(error) {
  const name = error?.name || ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return '摄像头权限被拒绝，请在浏览器地址栏中允许摄像头访问后重试'
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return '未检测到可用摄像头，请连接设备后重试'
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return '摄像头当前被其他应用占用，请关闭占用程序后重试'
  }
  if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError') {
    return '摄像头不支持当前视频参数，请更换设备后重试'
  }
  if (name === 'SecurityError') {
    return '当前页面安全策略禁止访问摄像头，请使用 HTTPS 或本机安全地址'
  }
  return error?.message || '摄像头启动失败'
}

export function releaseCameraResources({
  mediaStream,
  client,
  animationFrameId,
  cancelFrame = globalThis.cancelAnimationFrame,
}) {
  mediaStream?.getTracks?.().forEach((track) => {
    try {
      track.stop()
    } catch {}
  })
  try {
    client?.close?.()
  } catch {}
  if (animationFrameId !== null && animationFrameId !== undefined) {
    try {
      cancelFrame?.(animationFrameId)
    } catch {}
  }
}
