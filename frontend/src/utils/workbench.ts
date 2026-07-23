import type { Exercise, LessonStage, ProjectInput, Task } from '../types'

export function validateProject(form: ProjectInput): string | null {
  if (!form.name.trim()) return '请填写项目名称'
  if (!form.subject.trim() || !form.grade.trim()) return '请填写学科和年级'
  if (!form.lesson_topic.trim()) return '请填写课题'
  if (form.lesson_count < 1 || form.lesson_count > 8) return '课时数应为 1—8'
  if (!form.theme_id) return '请选择课件模板'
  return null
}

export const workbenchPath = (projectId: string) => `/workbench/${projectId}`
export const shouldPoll = (tasks: Task[]) => tasks.some(({ status }) => status === 'pending' || status === 'running')

const errorLabels: Record<string, string> = {
  SOURCE_NOT_READY: '资料尚未完成索引，请稍后重试',
  RETRIEVAL_EMPTY: '没有检索到可用资料，请检查知识库',
  MODEL_TIMEOUT: 'AI 模型响应超时，请稍后重试',
  STRUCTURE_VALIDATION_FAILED: '生成结果结构校验失败，请重新生成',
  INTERNAL_ERROR: '服务器暂时不可用，请稍后重试',
}

export const taskErrorText = (code?: string, message?: string) => errorLabels[code || ''] || message || '任务执行失败'
export const canRetryTask = ({ status }: Task) => status === 'failed' || status === 'cancelled'
export const currentTaskId = (tasks: Task[], saved = '') =>
  tasks.find(({ id }) => id === saved)?.id || tasks.find(({ status }) => status === 'pending' || status === 'running')?.id || tasks[0]?.id || ''
export const citationAvailable = (sourceId: string, sourceIds: string[]) => sourceIds.includes(sourceId)

export const totalMinutes = (stages: LessonStage[] = []) => stages.reduce((sum, item) => sum + item.time_minutes, 0)
export const showExerciseAnswers = (view: string) => view === '教师视图'
export const groupExercises = (items: Exercise[] = []) =>
  ['基础', '巩固', '提高'].map((level) => ({ level, items: items.filter((item) => item.level === level) }))

export function safeSlideHtml(markdown = '') {
  const text = markdown.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  return `<!doctype html><meta charset="utf-8"><style>body{margin:0;padding:36px;background:#102444;color:white;font:20px/1.7 sans-serif}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><pre>${text}</pre>`
}

export const issueTargetRoute = (projectId: string, targetId: string) => ({ path: `/workbench/${projectId}`, query: { target: targetId } })
export const canExport = (graphStatus: string) => graphStatus === 'succeeded'
export const exportProgress = (status: string) => ({ pending: 20, running: 60, succeeded: 100, failed: 0 })[status] ?? 0
export function elapsedText(start?: string, end?: string) {
  if (!start) return '暂无耗时'
  const seconds = Math.max(0, Math.round((new Date(end || Date.now()).getTime() - new Date(start).getTime()) / 1000))
  return `${seconds} 秒`
}

export const httpStatusText = (status?: number) => ({
  401: '登录状态已失效，请重新登录', 404: '请求的项目或内容不存在',
  409: '数据已发生变化，请刷新后重试', 500: '服务器暂时不可用，请稍后重试',
})[status || 0] || '暂时无法连接后端'
