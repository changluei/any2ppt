import { http } from './http'
import type { Artifact, ExportJob, GraphState, Project, ProjectInput, Skill, Task, TaskInput } from '../types'
export type { ProjectInput } from '../types'
export const api = {
  health: () => http.get('/health').then(r=>r.data),
  projects: () => http.get<Project[]>('/api/projects').then(r=>r.data),
  project: (id:string) => http.get<Project>(`/api/projects/${id}`).then(r=>r.data),
  createProject: (data:ProjectInput) => http.post<Project>('/api/projects',data).then(r=>r.data),
  skills: () => http.get<Skill[]>('/api/skills').then(r=>r.data),
  createTask: (id:string,data:TaskInput) => http.post<Task>(`/api/projects/${id}/tasks`,data).then(r=>r.data),
  tasks: (id:string) => http.get<Task[]>(`/api/projects/${id}/tasks`).then(r=>r.data),
  task: (id:string) => http.get<Task>(`/api/tasks/${id}`).then(r=>r.data),
  cancelTask: (id:string) => http.post<Task>(`/api/tasks/${id}/cancel`).then(r=>r.data),
  retryTask: (id:string) => http.post<Task>(`/api/tasks/${id}/retry`).then(r=>r.data),
  artifacts: (id:string) => http.get<Artifact[]>(`/api/projects/${id}/artifacts`).then(r=>r.data),
  revise: (id:string,data:Record<string,unknown>) => http.post<Artifact>(`/api/artifacts/${id}/revise`,data).then(r=>r.data),
  versions: (id:string) => http.get<Artifact[]>(`/api/artifacts/${id}/versions`).then(r=>r.data),
  rollback: (id:string,v:number) => http.post<Artifact>(`/api/artifacts/${id}/rollback/${v}`).then(r=>r.data),
  graph: (id:string) => http.get<GraphState>(`/api/projects/${id}/graph`).then(r=>r.data),
  startGraph: (id:string,taskId?:string) => http.post<GraphState>(`/api/projects/${id}/graph/runs`,{task_id:taskId}).then(r=>r.data),
  resumeGraph: (id:string) => http.post<GraphState>(`/api/graphs/${id}/resume`).then(r=>r.data),
  cancelGraph: (id:string) => http.post<GraphState>(`/api/graphs/${id}/cancel`).then(r=>r.data),
  confirmGraph: (id:string,decision:string) => http.post<{status:string;decision:string}>(`/api/graphs/${id}/confirm`,{decision}).then(r=>r.data),
  createExport: (id:string,package_type:string,artifact_version_ids:string[]=[]) => http.post<ExportJob>(`/api/projects/${id}/exports`,{package_type,artifact_version_ids}).then(r=>r.data),
  exportStatus: (id:string) => http.get<ExportJob>(`/api/exports/${id}`).then(r=>r.data),
  downloadExport: (id:string) => http.get<Blob>(`/api/exports/${id}/download`,{responseType:'blob'}).then(r=>({blob:r.data,filename:/filename="?([^";]+)"?/i.exec(r.headers['content-disposition']||'')?.[1]||'LessonDeck.zip'})),
}

