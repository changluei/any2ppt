/**
 * Axios 单例与统一响应防御。
 *
 * VITE_API_BASE_URL 未设置时使用本地后端；objectData/listData 可提前识别
 * “请求误打到前端 HTML”一类部署错误，拦截器则把后端 error 信封转换为
 * 页面统一使用的 ApiError。
 */
import axios from 'axios'
import type { ApiError } from '../types'
import { httpStatusText } from '../utils/workbench'
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || 'http://localhost:8000'
export const http = axios.create({ baseURL: apiBaseUrl, timeout: 30000 })
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
  // 保留 code、trace_id、409 当前版本，页面可给出可操作的错误提示。
  const payload = error.response?.data?.error
  const friendly = new Error(payload?.message || (error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : httpStatusText(error.response?.status))) as ApiError
  friendly.code = payload?.code || error.code; friendly.traceId = payload?.trace_id; friendly.status = error.response?.status; friendly.currentVersion = payload?.current_version
  return Promise.reject(friendly)
})
