import { http, listData, objectData } from './http'
import type { Artifact, ExportJob, GraphState, Project, ProjectInput, Skill, Task, TaskInput } from '../types'
export type { ProjectInput } from '../types'
export const api = {
  health: () => http.get('/health').then(r=>objectData<Record<string, unknown>>(r.data)),
  projects: () => http.get('/api/projects').then(r=>listData<Project>(r.data)),
  project: (id:string) => http.get(`/api/projects/${id}`).then(r=>objectData<Project>(r.data)),
  createProject: (data:ProjectInput) => http.post('/api/projects',data).then(r=>objectData<Project>(r.data)),
  skills: () => http.get('/api/skills').then(r=>listData<Skill>(r.data)),
  createTask: (id:string,data:TaskInput) => http.post(`/api/projects/${id}/tasks`,data).then(r=>objectData<Task>(r.data)),
  tasks: (id:string) => http.get(`/api/projects/${id}/tasks`).then(r=>listData<Task>(r.data)),
  task: (id:string) => http.get(`/api/tasks/${id}`).then(r=>objectData<Task>(r.data)),
  cancelTask: (id:string) => http.post(`/api/tasks/${id}/cancel`).then(r=>objectData<Task>(r.data)),
  retryTask: (id:string) => http.post(`/api/tasks/${id}/retry`).then(r=>objectData<Task>(r.data)),
  artifacts: (id:string) => http.get(`/api/projects/${id}/artifacts`).then(r=>listData<Artifact>(r.data)),
  revise: (id:string,data:Record<string,unknown>) => http.post(`/api/artifacts/${id}/revise`,data).then(r=>objectData<Artifact>(r.data)),
  versions: (id:string) => http.get(`/api/artifacts/${id}/versions`).then(r=>listData<Artifact>(r.data)),
  rollback: (id:string,v:number) => http.post(`/api/artifacts/${id}/rollback/${v}`).then(r=>objectData<Artifact>(r.data)),
  graph: (id:string) => http.get(`/api/projects/${id}/graph`).then(r=>objectData<GraphState>(r.data)),
  startGraph: (id:string,taskId?:string) => http.post(`/api/projects/${id}/graph/runs`,{task_id:taskId}).then(r=>objectData<GraphState>(r.data)),
  resumeGraph: (id:string) => http.post(`/api/graphs/${id}/resume`).then(r=>objectData<GraphState>(r.data)),
  cancelGraph: (id:string) => http.post(`/api/graphs/${id}/cancel`).then(r=>objectData<GraphState>(r.data)),
  confirmGraph: (id:string,decision:string) => http.post(`/api/graphs/${id}/confirm`,{decision}).then(r=>objectData<{status:string;decision:string}>(r.data)),
  createExport: (id:string,package_type:string,artifact_version_ids:string[]=[]) => http.post(`/api/projects/${id}/exports`,{package_type,artifact_version_ids}).then(r=>objectData<ExportJob>(r.data)),
  exportStatus: (id:string) => http.get(`/api/exports/${id}`).then(r=>objectData<ExportJob>(r.data)),
  downloadExport: (id:string) => http.get<Blob>(`/api/exports/${id}/download`,{responseType:'blob'}).then(r=>({blob:r.data,filename:/filename="?([^";]+)"?/i.exec(r.headers['content-disposition']||'')?.[1]||'LessonDeck.zip'})),
}

