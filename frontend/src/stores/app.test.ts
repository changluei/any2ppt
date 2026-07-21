import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../api'
import { useAppStore } from './app'

describe('app store health check', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('records a successful health response', async () => {
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', service: 'backend', version: '1.0.0' })
    const store = useAppStore()

    await store.checkHealth()

    expect(store.backend).toBe('online')
  })

  it('shows an offline state for connection failures', async () => {
    vi.spyOn(api, 'health').mockRejectedValue(new Error('暂时无法连接后端'))
    const store = useAppStore()

    await store.checkHealth()

    expect(store.backend).toBe('offline')
    expect(store.healthError).toBe('暂时无法连接后端')
  })

  it('distinguishes a timeout from other failures', async () => {
    const timeout = Object.assign(new Error('请求超时，请稍后重试'), { code: 'ECONNABORTED' })
    vi.spyOn(api, 'health').mockRejectedValue(timeout)
    const store = useAppStore()

    await store.checkHealth()

    expect(store.backend).toBe('timeout')
  })
})
