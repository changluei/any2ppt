import { defineStore } from 'pinia'
import { api } from '../api'
export const useAppStore = defineStore('app',{ state:()=>({backend:'checking' as 'checking'|'online'|'offline',currentProjectId:''}), actions:{async checkHealth(){this.backend='checking';try{await api.health();this.backend='online'}catch{this.backend='offline'}}} })

