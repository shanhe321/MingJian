/**
 * cameraWs.js — 摄像头实时检测 WebSocket 工具
 *
 * 封装 WebSocket 连接、帧发送、结果处理等逻辑，
 * 对外提供简洁的 API，让组件专注于页面渲染。
 *
 * 使用方式：
 *   import { createCameraWs } from '@/utils/cameraWs';
 *
 *   const ws = createCameraWs({
 *     mode: 'cpu',
 *     conf: 0.25,
 *     onResult: (data) => { ... },
 *     onConfigOk: () => { ... },
 *     onError: (msg) => { ... },
 *     onClose: () => { ... },
 *   });
 *
 *   ws.connect();
 *   ws.sendFrame(base64Data);
 *   ws.close();
 */

class CameraWs {
  constructor(options) {
    this.ws = null
    this.isConnected = false

    this.mode = options.mode || 'cpu'
    this.conf = options.conf || 0.25
    this.iou = options.iou || 0.45
    this.sceneId = options.sceneId
    this.token = options.token || ''

    this.onResult = options.onResult || (() => {})
    this.onConfigOk = options.onConfigOk || (() => {})
    this.onError = options.onError || (() => {})
    this.onClose = options.onClose || (() => {})
  }

  /**
   * 建立 WebSocket 连接
   */
  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.warn('[CameraWs] 已存在活跃连接')
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    if (!this.token) {
      this.onError('登录状态无效，请重新登录')
      return
    }
    const wsUrl = `${protocol}//${host}/api/detection/camera?token=${encodeURIComponent(this.token)}`

    this.ws = new WebSocket(wsUrl)

    this.ws.onopen = () => {
      this.isConnected = true
      this.ws.send(
        JSON.stringify({
          type: 'config',
          mode: this.mode,
          conf: this.conf,
          iou: this.iou,
          scene_id: this.sceneId,
        }),
      )
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this._handleMessage(data)
      } catch (err) {
        console.error('[CameraWs] 消息解析失败:', err)
      }
    }

    this.ws.onclose = (event) => {
      this.isConnected = false
      if (event.code === 1008) this.onError(event.reason || '摄像头连接认证失败')
      this.onClose()
    }

    this.ws.onerror = (err) => {
      console.error('[CameraWs] 连接错误:', err)
      this.onError('WebSocket 连接失败，请检查后端服务')
    }
  }

  /**
   * 发送一帧数据
   * @param {string} base64Data - 帧数据的 Base64 字符串（不含前缀）
   */
  sendFrame(base64Data) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[CameraWs] 连接未建立')
      return false
    }

    if (!base64Data) {
      return false
    }

    this.ws.send(
      JSON.stringify({
        type: 'frame',
        data: base64Data,
      }),
    )
    return true
  }

  /**
   * 关闭连接
   */
  close() {
    const socket = this.ws
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'close' }))
    }
    if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) {
      socket.close()
    }
    this.ws = null
    this.isConnected = false
  }

  /**
   * 更新配置（需要重新连接）
   */
  updateConfig(config) {
    this.mode = config.mode || this.mode
    this.conf = config.conf || this.conf
    this.iou = config.iou || this.iou
    this.sceneId = config.sceneId
    this.token = config.token || this.token
  }

  /**
   * 处理后端消息
   */
  _handleMessage(data) {
    switch (data.type) {
      case 'result':
        this.onResult({
          annotatedFrame: data.annotated_frame,
          detections: data.detections || [],
          objectCount: data.object_count || 0,
          inferenceTime: data.inference_time || 0,
          fps: data.fps || 0,
          frameCount: data.frame_count || 0,
        })
        break

      case 'config_ok':
        this.onConfigOk(data)
        break

      case 'error':
        console.error('[CameraWs] 服务端错误:', data.message)
        this.onError(data.message)
        break

      default:
        console.warn('[CameraWs] 未知消息类型:', data.type)
    }
  }
}

/**
 * 创建摄像头 WebSocket 实例
 * @param {object} options
 * @returns {CameraWs}
 */
export function createCameraWs(options) {
  return new CameraWs(options)
}
