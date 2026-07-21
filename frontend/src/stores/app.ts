import { defineStore } from 'pinia'
import { api } from '../api'

export type BackendHealth = 'checking' | 'online' | 'offline' | 'timeout'
type RequestError = Error & { code?: string }

export const useAppStore = defineStore('app', {
  state: () => ({
    backend: 'checking' as BackendHealth,
    healthError: '',
  }),
  actions: {
    async checkHealth() {
      this.backend = 'checking'
      this.healthError = ''

      try {
        await api.health()
        this.backend = 'online'
      } catch (error) {
        const requestError = error as RequestError
        const timedOut = requestError.code === 'ECONNABORTED' || requestError.message.includes('超时')
        this.backend = timedOut ? 'timeout' : 'offline'
        this.healthError = requestError.message
      }
    },
  },
})

