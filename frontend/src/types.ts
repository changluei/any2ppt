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
  theme_id: string
  theme_status: 'selected' | 'preparing' | 'ready' | 'failed'
  status: string
  created_at: string
  updated_at: string
}

export type ProjectInput = Omit<Project, 'id' | 'status' | 'theme_status' | 'created_at' | 'updated_at'>
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
  score?: number
}

export type ThemeDescriptor = {
  id: string
  name: string
  package: string
  version: string
  description: string
  keywords: string[]
  preview_url: string
  source_url: string
  layouts: string[]
  design_guidance: string
  density: 'low' | 'medium' | 'high'
  image_strategy: string
  theme_config: Record<string, string>
  palette: { background: string; surface: string; text: string; accent: string }
}
export type ProjectImage = {
  id: string
  project_id: string
  original_name: string
  media_type: string
  size: number
  width: number
  height: number
  content_url: string
  created_at: string
}
export type SlideImagePlacement = {
  placement_id: string
  image_id: string
  original_name: string
  position: 'left' | 'right' | 'center' | 'wide' | 'background'
  caption?: string
  x: number
  y: number
  width: number
  height: number
  opacity: number
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
  result_snapshot?: {
    skill_id?: string
    result?: Record<string, unknown>
    citations?: Citation[]
    warnings?: string[]
    degraded?: boolean
    trace?: Record<string, unknown>
    kind?: string
  }
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

export type Objective = { id: string; behavior: string; condition?: string; criterion?: string; core?: boolean }
export type LessonStage = {
  id: string
  name: string
  time_minutes: number
  teacher_actions: string
  student_actions: string
  objective_ids?: string[]
  assessment?: string
}
export type Assessment = { id: string; method: string; objective_ids: string[]; success_criteria: string }
export type Slide = {
  slide_id: string
  order: number
  title: string
  layout?: string
  markdown: string
  teaching_stage: string
  objective_ids?: string[]
  citations?: Citation[]
  speaker_note?: Partial<SpeakerNote>
  images?: SlideImagePlacement[]
}
export type SpeakerNote = {
  slide_id: string
  explanation: string
  questions: string[]
  expected_answers?: string[]
  transition: string
  board_notes: string
  estimated_minutes?: number
}
export type Exercise = {
  exercise_id: string
  level: string
  objective_ids?: string[]
  question: string
  type?: string
  difficulty?: number
  answer: string
  explanation: string
  source?: string
  needs_teacher_review: boolean
  citations?: Citation[]
}
export type ArtifactContent = {
  title?: string
  deck_title?: string
  objectives?: Objective[]
  key_points?: string[]
  difficult_points?: string[]
  stages?: LessonStage[]
  assessments?: Assessment[]
  teaching_strategies?: string[]
  slides?: Slide[]
  notes?: SpeakerNote[]
  exercises?: Exercise[]
  theme?: string
  theme_id?: string
  theme_name?: string
  theme_version?: string
  theme_description?: string
  theme_match_reason?: string
  theme_palette?: ThemeDescriptor['palette']
  theme_preview_url?: string
  theme_source_url?: string
  theme_layouts?: string[]
  theme_design_guidance?: string
  theme_image_strategy?: string
  theme_density?: ThemeDescriptor['density']
  theme_config?: Record<string, string>
}
export type ArtifactType = 'lesson_plan' | 'slide_deck' | 'speaker_notes' | 'exercise_set'
export type Artifact = {
  artifact_id: string
  version_id: string
  project_id: string
  type: ArtifactType
  version_no: number
  parent_version_id?: string
  change_type: string
  changed_ids: string[]
  unchanged_hashes: Array<{ id: string; sha256: string }>
  content: ArtifactContent
  citations: Citation[]
  warnings: string[]
  created_at: string
}

export type GraphState = {
  id?: string
  project_id?: string
  task_id?: string
  thread_id?: string
  checkpoint_ref?: string
  attempt?: number
  status: string
  current_node?: string | null
  nodes: Array<{ node_id: string; status: string; attempt: number; started_at?: string; finished_at?: string; issues?: string[] }>
  issues: QualityIssue[]
  state_snapshot?: {
    repair_scope?: string
    degraded?: boolean
    model?: string
    elapsed_ms?: number
    recovery_message?: string
    error?: string
    checkpointed_at?: string
  }
  human_decision?: string
  created_at?: string
  updated_at?: string
}
export type QualityIssue = { issue_type: string; target_id: string; severity: string; suggestion: string }
export type ExportJob = {
  job_id: string
  project_id?: string
  package_type?: 'teacher' | 'student' | 'pptx'
  selected_versions?: Record<string, string>
  status: string
  error_message?: string
  download_url?: string
}
export type ApiError = Error & { code?: string; traceId?: string; status?: number; currentVersion?: number }
