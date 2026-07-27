import type { ProjectInput } from '../types'

const storageKey = 'any2ppt:active-generation'

export type GenerationSession = {
  mode: 'create' | 'regenerate'
  projectId: string
  prompt: string
  form?: ProjectInput
  sourceIds: string[]
  uploadedSourceIds: string[]
  expectedFileCount: number
  idempotencyKey: string
  taskId: string
  files: File[]
}

type StoredGenerationSession = Omit<GenerationSession, 'files'>

let activeSession: GenerationSession | undefined

function persist(session: GenerationSession) {
  const stored: StoredGenerationSession = {
    mode: session.mode,
    projectId: session.projectId,
    prompt: session.prompt,
    form: session.form,
    sourceIds: session.sourceIds,
    uploadedSourceIds: session.uploadedSourceIds,
    expectedFileCount: session.expectedFileCount,
    idempotencyKey: session.idempotencyKey,
    taskId: session.taskId,
  }
  window.sessionStorage.setItem(storageKey, JSON.stringify(stored))
}

export function beginGenerationSession(
  input: Pick<GenerationSession, 'mode' | 'prompt'> &
    Partial<Pick<GenerationSession, 'projectId' | 'form' | 'sourceIds' | 'files'>>,
) {
  const files = [...(input.files || [])]
  activeSession = {
    mode: input.mode,
    projectId: input.projectId || '',
    prompt: input.prompt,
    form: input.form,
    sourceIds: [...(input.sourceIds || [])],
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
  if (activeSession) return activeSession
  const raw = window.sessionStorage.getItem(storageKey)
  if (!raw) return undefined
  try {
    const stored = JSON.parse(raw) as StoredGenerationSession
    activeSession = { ...stored, files: [] }
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
  activeSession = undefined
  window.sessionStorage.removeItem(storageKey)
}
