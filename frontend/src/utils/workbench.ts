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
