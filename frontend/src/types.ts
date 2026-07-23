export type Project = {
  id: string
  name: string
  subject: string
  grade: string
  textbook_version: string
  lesson_topic: string
  lesson_count: number
  student_profile: string
  teacher_requirements: string
  status: string
  created_at: string
  updated_at: string
}

export type ProjectInput = Omit<Project, 'id' | 'status' | 'created_at' | 'updated_at'>
export type SourceStatus = 'uploaded' | 'parsing' | 'indexing' | 'ready' | 'failed'
export type Source = {
  id: string
  project_id: string
  original_name: string
  media_type: string
  size: number
  status: SourceStatus
  error_message: string | null
  created_at: string
  updated_at: string
}
export type SearchResult = {
  content: string
  source_id: string
  chunk_id: string
  filename: string
  location: string
  score: number
}
export type Citation = {
  source_id: string
  chunk_id: string
  filename: string
  location: string
  quote: string
}

export type Skill = { id: string; name: string; description: string; required_inputs: string[] }
export type TaskStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'
export type Task = {
  id: string
  project_id: string
  type: string
  status: TaskStatus
  stage: string
  progress: number
  trace_id: string
  result_artifact_id?: string
  error_code?: string
  error_message?: string
  started_at?: string
  finished_at?: string
  created_at: string
  updated_at: string
}
export type TaskInput = {
  type: string
  selected_source_ids: string[]
  teacher_requirements: string
  idempotency_key: string
}

export type Objective = { id: string; behavior: string; condition?: string; criterion?: string }
export type LessonStage = {
  id: string
  name: string
  time_minutes: number
  teacher_actions: string
  student_actions: string
}
export type Slide = { slide_id: string; order: number; title: string; markdown: string; teaching_stage: string }
export type SpeakerNote = {
  slide_id: string
  explanation: string
  questions: string[]
  transition: string
  board_notes: string
}
export type Exercise = {
  exercise_id: string
  level: string
  question: string
  answer: string
  explanation: string
  needs_teacher_review: boolean
}
export type ArtifactContent = {
  title?: string
  objectives?: Objective[]
  stages?: LessonStage[]
  slides?: Slide[]
  notes?: SpeakerNote[]
  exercises?: Exercise[]
}
export type ArtifactType = 'lesson_plan' | 'slide_deck' | 'speaker_notes' | 'exercise_set'
export type Artifact = {
  artifact_id: string
  version_id: string
  project_id: string
  type: ArtifactType
  version_no: number
  content: ArtifactContent
  citations: Citation[]
  warnings: string[]
  created_at: string
}

export type GraphState = {
  id?: string
  status: string
  current_node?: string
  nodes: Array<{ node_id: string; status: string; attempt: number }>
  issues: Array<{ issue_type: string; target_id: string; severity: string; suggestion: string }>
}
export type ExportJob = { job_id: string; status: string; error_message?: string }
export type ApiError = Error & { code?: string; traceId?: string; status?: number; currentVersion?: number }
