/**
 * Vite 开发端口与生产分包。
 * Vue 运行时和 Element Plus 分离为稳定 chunk，业务改动不会让全部依赖失效。
 */
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue()], server: { port: 5173, host: true }, build:{rollupOptions:{output:{manualChunks:{vue:['vue','vue-router','pinia'],element:['element-plus','@element-plus/icons-vue']}}}} })
