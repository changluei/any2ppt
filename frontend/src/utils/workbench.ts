import type { ProjectInput, Task } from '../types'

export function validateProject(form: ProjectInput): string | null {
  if (!form.name.trim()) return '请填写项目名称'
  if (!form.subject.trim() || !form.grade.trim()) return '请填写学科和年级'
  if (!form.lesson_topic.trim()) return '请填写课题'
  if (form.lesson_count < 1 || form.lesson_count > 8) return '课时数应为 1—8'
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
