import { http } from './http'
import type { Project, Source, Task, Artifact, GraphState } from '../types'
export type ProjectInput = Omit<Project,'id'|'status'|'created_at'|'updated_at'>
export const api = {
  health: () => http.get('/health').then(r=>r.data),
  projects: () => http.get<Project[]>('/api/projects').then(r=>r.data),
  project: (id:string) => http.get<Project>(`/api/projects/${id}`).then(r=>r.data),
  createProject: (data:ProjectInput) => http.post<Project>('/api/projects',data).then(r=>r.data),
  sources: (id:string) => http.get<Source[]>(`/api/projects/${id}/sources`).then(r=>r.data),
  upload: (id:string,file:File,onProgress?:(v:number)=>void) => { const form=new FormData(); form.append('file',file); return http.post<Source>(`/api/projects/${id}/sources`,form,{onUploadProgress:e=>onProgress?.(e.total?Math.round(e.loaded/e.total*100):0)}).then(r=>r.data) },
  retrySource: (pid:string,sid:string) => http.post(`/api/projects/${pid}/sources/${sid}/index`).then(r=>r.data),
  deleteSource: (pid:string,sid:string) => http.delete(`/api/projects/${pid}/sources/${sid}`),
  search: (id:string,query:string,top_k=5) => http.post(`/api/projects/${id}/search`,{query,top_k}).then(r=>r.data),
  skills: () => http.get('/api/skills').then(r=>r.data),
  createTask: (id:string,data:Record<string,unknown>) => http.post<Task>(`/api/projects/${id}/tasks`,data).then(r=>r.data),
  tasks: (id:string) => http.get<Task[]>(`/api/projects/${id}/tasks`).then(r=>r.data),
  task: (id:string) => http.get<Task>(`/api/tasks/${id}`).then(r=>r.data),
  cancelTask: (id:string) => http.post<Task>(`/api/tasks/${id}/cancel`).then(r=>r.data),
  artifacts: (id:string) => http.get<Artifact[]>(`/api/projects/${id}/artifacts`).then(r=>r.data),
  revise: (id:string,data:Record<string,unknown>) => http.post<Artifact>(`/api/artifacts/${id}/revise`,data).then(r=>r.data),
  versions: (id:string) => http.get<Artifact[]>(`/api/artifacts/${id}/versions`).then(r=>r.data),
  rollback: (id:string,v:number) => http.post<Artifact>(`/api/artifacts/${id}/rollback/${v}`).then(r=>r.data),
  graph: (id:string) => http.get<GraphState>(`/api/projects/${id}/graph`).then(r=>r.data),
  confirmGraph: (id:string,decision:string) => http.post(`/api/graphs/${id}/confirm`,{decision}).then(r=>r.data),
  createExport: (id:string,package_type:string) => http.post(`/api/projects/${id}/exports`,{package_type}).then(r=>r.data),
  exportStatus: (id:string) => http.get(`/api/exports/${id}`).then(r=>r.data),
  downloadUrl: (id:string) => `${http.defaults.baseURL}/api/exports/${id}/download`,
}

