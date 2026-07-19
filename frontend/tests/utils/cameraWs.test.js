import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createCameraWs } from '@/utils/cameraWs'

class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = 0
    this.sent = []
    MockWebSocket.instances.push(this)
  }

  send(payload) {
    this.sent.push(payload)
  }

  close() {
    this.closed = true
  }
}

describe('浏览器摄像头 WebSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    window.happyDOM.setURL('https://cloud.example.com/detection')
  })

  it('使用当前网页域名、WSS 和编码后的 JWT', () => {
    const client = createCameraWs({ token: 'token with spaces' })
    client.connect()

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toBe(
      'wss://cloud.example.com/api/detection/camera?token=token%20with%20spaces',
    )
    expect(MockWebSocket.instances[0].url).not.toContain('localhost')
  })

  it('没有登录 Token 时拒绝连接', () => {
    const onError = vi.fn()
    createCameraWs({ token: '', onError }).connect()

    expect(MockWebSocket.instances).toHaveLength(0)
    expect(onError).toHaveBeenCalledWith('登录状态无效，请重新登录')
  })

  it('连接后原样发送设备、阈值和场景配置', () => {
    const client = createCameraWs({
      token: 'camera-token',
      mode: 'gpu',
      conf: 0.4,
      iou: 0.55,
      sceneId: 7,
    })
    client.connect()
    const socket = MockWebSocket.instances[0]
    socket.readyState = MockWebSocket.OPEN
    socket.onopen()

    expect(JSON.parse(socket.sent[0])).toEqual({
      type: 'config',
      mode: 'gpu',
      conf: 0.4,
      iou: 0.55,
      scene_id: 7,
    })
  })

  it('路由离开时即使仍在连接也会关闭底层 WebSocket', () => {
    const client = createCameraWs({ token: 'camera-token' })
    client.connect()
    const socket = MockWebSocket.instances[0]

    client.close()

    expect(socket.closed).toBe(true)
    expect(client.isConnected).toBe(false)
  })
})
