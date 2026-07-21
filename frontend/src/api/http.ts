import axios from 'axios'
export const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000', timeout: 30000 })
http.interceptors.response.use(r => r, error => {
  const payload = error.response?.data?.error
  const friendly = new Error(payload?.message || (error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : '暂时无法连接后端')) as Error & { code?:string; traceId?:string; status?:number }
  friendly.code = payload?.code || error.code; friendly.traceId = payload?.trace_id; friendly.status = error.response?.status
  return Promise.reject(friendly)
})

