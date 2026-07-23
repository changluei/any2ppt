import { describe, expect, it } from 'vitest'
import type { ProjectInput, Task } from '../types'
import { shouldPoll, validateProject, workbenchPath } from './workbench'

const form: ProjectInput = {
  name: '测试项目', subject: '语文', grade: '三年级', textbook_version: '',
  lesson_topic: '测试课题', lesson_count: 1, student_profile: '', teacher_requirements: '',
}

describe('day 3 workbench helpers', () => {
  it('validates required project fields', () => {
    expect(validateProject(form)).toBeNull()
    expect(validateProject({ ...form, lesson_topic: ' ' })).toBe('请填写课题')
  })

  it('builds the success redirect path', () => {
    expect(workbenchPath('project-1')).toBe('/workbench/project-1')
  })

  it('polls only while a task is active', () => {
    const task = (status: Task['status']) => ({ status }) as Task
    expect(shouldPoll([task('running')])).toBe(true)
    expect(shouldPoll([task('succeeded'), task('failed')])).toBe(false)
  })
})
