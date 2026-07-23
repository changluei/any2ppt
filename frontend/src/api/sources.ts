import { http, listData, objectData } from './http'
import type { SearchResult, Source } from '../types'

export const sourcesApi = {
  list: (projectId: string) =>
    http.get(`/api/projects/${projectId}/sources`).then(({ data }) => listData<Source>(data)),
  upload: (projectId: string, file: File, progress: (value: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    return http
      .post<Source>(`/api/projects/${projectId}/sources`, form, {
        onUploadProgress: ({ loaded, total }) => progress(total ? Math.round((loaded / total) * 100) : 0),
      })
      .then(({ data }) => objectData<Source>(data))
  },
  retry: (projectId: string, sourceId: string) =>
    http.post(`/api/projects/${projectId}/sources/${sourceId}/index`).then(({ data }) => objectData<Source>(data)),
  remove: (projectId: string, sourceId: string) =>
    http.delete(`/api/projects/${projectId}/sources/${sourceId}`),
  search: (projectId: string, query: string, topK: number) =>
    http
      .post(`/api/projects/${projectId}/search`, { query, top_k: topK })
      .then(({ data }) => listData<SearchResult>(data)),
}
