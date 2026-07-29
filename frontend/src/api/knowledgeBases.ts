/** 四类知识库目录、个人资料生命周期与多库检索请求。 */
import { http, listData, objectData } from './http'
import type { KnowledgeBase, SearchResult, Source } from '../types'

export const knowledgeBasesApi = {
  list: () => http.get('/api/knowledge-bases').then(({ data }) => listData<KnowledgeBase>(data)),
  sources: (knowledgeBaseId: string) =>
    http.get(`/api/knowledge-bases/${knowledgeBaseId}/sources`).then(({ data }) => listData<Source>(data)),
  source: (sourceId: string) =>
    http.get(`/api/knowledge-bases/personal/sources/${sourceId}`).then(({ data }) => objectData<Source>(data)),
  upload: (file: File, progress: (value: number) => void, projectId?: string) => {
    const form = new FormData()
    form.append('file', file)
    return http
      .post<Source>('/api/knowledge-bases/personal/sources', form, {
        params: projectId ? { project_id: projectId } : undefined,
        onUploadProgress: ({ loaded, total }) => progress(total ? Math.round((loaded / total) * 100) : 0),
      })
      .then(({ data }) => objectData<Source>(data))
  },
  retry: (sourceId: string) =>
    http.post(`/api/knowledge-bases/personal/sources/${sourceId}/index`).then(({ data }) => objectData<Source>(data)),
  remove: (sourceId: string) => http.delete(`/api/knowledge-bases/personal/sources/${sourceId}`),
  search: (knowledgeBaseIds: string[], query: string, topK: number) =>
    http
      .post('/api/knowledge-bases/search', { knowledge_base_ids: knowledgeBaseIds, query, top_k: topK })
      .then(({ data }) => listData<SearchResult>(data)),
}
