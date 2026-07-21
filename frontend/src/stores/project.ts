import { defineStore } from 'pinia'

export const useProjectStore = defineStore('project', {
  state: () => ({ currentProjectId: '' }),
  actions: {
    select(id: string) {
      this.currentProjectId = id
    },
  },
})
