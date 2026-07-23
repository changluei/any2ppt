import { http, listData, objectData } from './http'
import type { ProjectImage } from '../types'

export const imagesApi = {
  list: (projectId: string) =>
    http.get(`/api/projects/${projectId}/images`).then(({ data }) => listData<ProjectImage>(data)),
  upload: (projectId: string, file: File, progress: (value: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    return http
      .post(`/api/projects/${projectId}/images`, form, {
        onUploadProgress: ({ loaded, total }) => progress(total ? Math.round((loaded / total) * 100) : 0),
      })
      .then(({ data }) => objectData<ProjectImage>(data))
  },
  url: (imageId: string) =>
    new URL(`/api/images/${imageId}/content`, http.defaults.baseURL || window.location.origin).toString(),
  baseUrl: () =>
    new URL('/api/images', http.defaults.baseURL || window.location.origin).toString().replace(/\/$/, ''),
}
