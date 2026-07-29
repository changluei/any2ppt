/** 当前项目选择的极小 Pinia store，供跨页面返回/跳转复用。 */
import { defineStore } from 'pinia'

export const useProjectStore = defineStore('project', {
  state: () => ({ currentProjectId: '' }),
  actions: {
    select(id: string) {
      this.currentProjectId = id
    },
  },
})
