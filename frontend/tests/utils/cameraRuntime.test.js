import { describe, expect, it, vi } from 'vitest'
import {
  cameraAccessErrorMessage,
  createCameraRuntimeState,
  getContainedFrameCrop,
  nextCameraRuntimeState,
  releaseCameraResources,
} from '@/utils/cameraRuntime'

describe('摄像头运行状态', () => {
  it('只在真实事件到达后依次标记摄像头和推理通道已连接', () => {
    let state = nextCameraRuntimeState(createCameraRuntimeState(), 'start')
    expect(state).toMatchObject({ camera: 'requesting', inference: 'idle' })

    state = nextCameraRuntimeState(state, 'camera_ready')
    expect(state).toMatchObject({ camera: 'connected', inference: 'connecting' })

    state = nextCameraRuntimeState(state, 'inference_ready')
    expect(state).toMatchObject({ camera: 'connected', inference: 'connected' })

    state = nextCameraRuntimeState(state, 'stop')
    expect(state).toEqual(createCameraRuntimeState())
  })

  it('为常见摄像头错误返回准确提示', () => {
    expect(cameraAccessErrorMessage({ name: 'NotAllowedError' })).toContain('权限被拒绝')
    expect(cameraAccessErrorMessage({ name: 'NotFoundError' })).toContain('未检测到')
    expect(cameraAccessErrorMessage({ name: 'NotReadableError' })).toContain('占用')
  })

  it('路由离开复用的释放函数会停止轨道、关闭 WS 并取消动画帧', () => {
    const stop = vi.fn()
    const close = vi.fn()
    const cancelFrame = vi.fn()

    releaseCameraResources({
      mediaStream: { getTracks: () => [{ stop }, { stop }] },
      client: { close },
      animationFrameId: 18,
      cancelFrame,
    })

    expect(stop).toHaveBeenCalledTimes(2)
    expect(close).toHaveBeenCalledOnce()
    expect(cancelFrame).toHaveBeenCalledWith(18)
  })

  it('将方形推理帧中的 letterbox 区域还原为摄像头真实比例', () => {
    expect(getContainedFrameCrop(1280, 720, 640, 640)).toEqual({
      x: 0,
      y: 140,
      width: 640,
      height: 360,
    })
    expect(getContainedFrameCrop(640, 480, 416, 416)).toEqual({
      x: 0,
      y: 52,
      width: 416,
      height: 312,
    })
  })

  it('无效视频尺寸不会产生错误坐标', () => {
    expect(getContainedFrameCrop(0, 720, 640, 640)).toBeNull()
  })
})
