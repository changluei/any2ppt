/**
 * 跨路由保存一次生成链路的客户端会话。
 *
 * File 对象不能序列化，只保存在内存；其余 ID、幂等键和选择写入
 * sessionStorage，刷新后 GenerationPage 可以继续轮询已创建的后端任务。
 */
import type { ProjectInput } from '../types'

const storageKey = 'any2ppt:active-generation'

export type GenerationSession = {
  mode: 'create' | 'regenerate'
  projectId: string
  prompt: string
  form?: ProjectInput
  sourceIds: string[]
  knowledgeBaseIds: string[]
  uploadedSourceIds: string[]
  expectedFileCount: number
  idempotencyKey: string
  taskId: string
  files: File[]
}

type StoredGenerationSession = Omit<GenerationSession, 'files'>

let activeSession: GenerationSession | undefined

function persist(session: GenerationSession) {
  // 明确挑选可序列化字段，避免误把 File 内容或临时对象写入浏览器存储。
  const stored: StoredGenerationSession = {
    mode: session.mode,
    projectId: session.projectId,
    prompt: session.prompt,
    form: session.form,
    sourceIds: session.sourceIds,
    knowledgeBaseIds: session.knowledgeBaseIds,
    uploadedSourceIds: session.uploadedSourceIds,
    expectedFileCount: session.expectedFileCount,
    idempotencyKey: session.idempotencyKey,
    taskId: session.taskId,
  }
  window.sessionStorage.setItem(storageKey, JSON.stringify(stored))
}

export function beginGenerationSession(
  input: Pick<GenerationSession, 'mode' | 'prompt'> &
    Partial<Pick<GenerationSession, 'projectId' | 'form' | 'sourceIds' | 'knowledgeBaseIds' | 'files'>>,
) {
  // 路由锁保证正常 UI 不会并发开始第二次会话。
  const files = [...(input.files || [])]
  activeSession = {
    mode: input.mode,
    projectId: input.projectId || '',
    prompt: input.prompt,
    form: input.form,
    sourceIds: [...(input.sourceIds || [])],
    knowledgeBaseIds: [...(input.knowledgeBaseIds || input.form?.knowledge_base_ids || [])],
    uploadedSourceIds: [],
    expectedFileCount: files.length,
    idempotencyKey: `generation-${crypto.randomUUID()}`,
    taskId: '',
    files,
  }
  persist(activeSession)
  return activeSession
}

export function getGenerationSession(): GenerationSession | undefined {
  // 优先返回含 File 的内存对象；刷新后再恢复可序列化的轮询状态。
  if (activeSession) return activeSession
  const raw = window.sessionStorage.getItem(storageKey)
  if (!raw) return undefined
  try {
    const stored = JSON.parse(raw) as StoredGenerationSession
    activeSession = { ...stored, knowledgeBaseIds: stored.knowledgeBaseIds || [], files: [] }
    return activeSession
  } catch {
    window.sessionStorage.removeItem(storageKey)
    return undefined
  }
}

export function updateGenerationSession(patch: Partial<GenerationSession>) {
  const current = getGenerationSession()
  if (!current) return undefined
  activeSession = { ...current, ...patch }
  persist(activeSession)
  return activeSession
}

export function hasActiveGeneration() {
  return Boolean(activeSession || window.sessionStorage.getItem(storageKey))
}

export function clearGenerationSession() {
  // 同时清理内存和 sessionStorage 才会解除全局导航锁。
  activeSession = undefined
  window.sessionStorage.removeItem(storageKey)
}
