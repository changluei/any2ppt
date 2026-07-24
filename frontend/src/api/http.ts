import axios from 'axios'
import type { ApiError } from '../types'
import { httpStatusText } from '../utils/workbench'
export const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '', timeout: 30000 })
const responseError = '接口响应格式异常，请检查 VITE_API_BASE_URL 配置'
export const objectData = <T>(data: unknown): T => {
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error(responseError)
  return data as T
}
export const listData = <T>(data: unknown): T[] => {
  if (!Array.isArray(data)) throw new Error(responseError)
  return data as T[]
}
http.interceptors.response.use(r => r, error => {
  const payload = error.response?.data?.error
  const friendly = new Error(payload?.message || (error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : httpStatusText(error.response?.status))) as ApiError
  friendly.code = payload?.code || error.code; friendly.traceId = payload?.trace_id; friendly.status = error.response?.status; friendly.currentVersion = payload?.current_version
  return Promise.reject(friendly)
})

