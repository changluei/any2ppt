import { http, listData, objectData } from './http'
import type { Artifact, ExportJob, GraphState, Project, ProjectInput, Skill, Task, TaskInput, ThemeDescriptor } from '../types'
export type { ProjectInput } from '../types'
export const api = {
  health: () => http.get('/health').then(r=>objectData<Record<string, unknown>>(r.data)),
  projects: () => http.get('/api/projects').then(r=>listData<Project>(r.data)),
  project: (id:string) => http.get(`/api/projects/${id}`).then(r=>objectData<Project>(r.data)),
  createProject: (data:ProjectInput) => http.post('/api/projects',data).then(r=>objectData<Project>(r.data)),
  updateProject: (id:string,data:ProjectInput) => http.put(`/api/projects/${id}`,data).then(r=>objectData<Project>(r.data)),
  deleteProject: (id:string,force=true) => http.delete(`/api/projects/${id}`,{params:{force}}),
  prepareProjectTheme: (id:string) => http.post(`/api/projects/${id}/theme/prepare`).then(r=>objectData<Project>(r.data)),
  skills: () => http.get('/api/skills').then(r=>listData<Skill>(r.data)),
  themes: () => http.get('/api/themes').then(r=>listData<ThemeDescriptor>(r.data)),
  recommendTheme: (data:Pick<ProjectInput,'subject'|'grade'|'lesson_topic'|'student_profile'|'teacher_requirements'>) => http.post('/api/themes/recommend',data).then(r=>objectData<ThemeDescriptor & {match_reason:string}>(r.data)),
  createTask: (id:string,data:TaskInput) => http.post(`/api/projects/${id}/tasks`,data).then(r=>objectData<Task>(r.data)),
  tasks: (id:string) => http.get(`/api/projects/${id}/tasks`).then(r=>listData<Task>(r.data)),
  task: (id:string) => http.get(`/api/tasks/${id}`).then(r=>objectData<Task>(r.data)),
  cancelTask: (id:string) => http.post(`/api/tasks/${id}/cancel`).then(r=>objectData<Task>(r.data)),
  retryTask: (id:string) => http.post(`/api/tasks/${id}/retry`).then(r=>objectData<Task>(r.data)),
  artifacts: (id:string) => http.get(`/api/projects/${id}/artifacts`).then(r=>listData<Artifact>(r.data)),
  revise: (id:string,data:Record<string,unknown>) => http.post(`/api/artifacts/${id}/revise`,data).then(r=>objectData<Artifact>(r.data)),
  saveSlideMarkdown: (id:string,data:{base_version_no:number;slide_id:string;markdown:string}) => http.post(`/api/artifacts/${id}/markdown`,data).then(r=>objectData<Artifact>(r.data)),
  placeSlideImage: (id:string,data:{base_version_no:number;slide_id:string;image_id:string;position:string;caption:string}) => http.post(`/api/artifacts/${id}/images`,data).then(r=>objectData<Artifact>(r.data)),
  removeSlideImage: (id:string,placementId:string,baseVersionNo:number) => http.delete(`/api/artifacts/${id}/images/${placementId}`,{params:{base_version_no:baseVersionNo}}).then(r=>objectData<Artifact>(r.data)),
  versions: (id:string) => http.get(`/api/artifacts/${id}/versions`).then(r=>listData<Artifact>(r.data)),
  rollback: (id:string,v:number) => http.post(`/api/artifacts/${id}/rollback/${v}`).then(r=>objectData<Artifact>(r.data)),
  graph: (id:string) => http.get(`/api/projects/${id}/graph`).then(r=>objectData<GraphState>(r.data)),
  startGraph: (id:string,taskId?:string) => http.post(`/api/projects/${id}/graph/runs`,{task_id:taskId}).then(r=>objectData<GraphState>(r.data)),
  resumeGraph: (id:string) => http.post(`/api/graphs/${id}/resume`).then(r=>objectData<GraphState>(r.data)),
  cancelGraph: (id:string) => http.post(`/api/graphs/${id}/cancel`).then(r=>objectData<GraphState>(r.data)),
  confirmGraph: (id:string,decision:string) => http.post(`/api/graphs/${id}/confirm`,{decision}).then(r=>objectData<{status:string;decision:string}>(r.data)),
  createExport: (id:string,package_type:string,artifact_version_ids:string[]=[]) => http.post(`/api/projects/${id}/exports`,{package_type,artifact_version_ids}).then(r=>objectData<ExportJob>(r.data)),
  exportStatus: (id:string) => http.get(`/api/exports/${id}`).then(r=>objectData<ExportJob>(r.data)),
  downloadExport: (id:string) => http.get<Blob>(`/api/exports/${id}/download`,{responseType:'blob'}).then(r => {
    const disposition = r.headers['content-disposition'] || ''
    const encoded = /filename\*=utf-8''([^;]+)/i.exec(disposition)?.[1]
    const plain = /filename="?([^";]+)"?/i.exec(disposition)?.[1]
    const isPptx = String(r.headers['content-type']).includes('presentationml.presentation')
    return { blob: r.data, filename: encoded ? decodeURIComponent(encoded) : plain || (isPptx ? '备课课件.pptx' : '备课资料.zip') }
  }),
}
