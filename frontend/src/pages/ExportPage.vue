<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import type { ApiError, Artifact, ArtifactType, ExportJob, GraphState } from '../types'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import StatusTag from '../components/StatusTag.vue'
import { canExport, exportProgress } from '../utils/workbench'

const router = useRouter()
const projectId = String(useRoute().params.projectId)
const graph = ref<GraphState>({ status: 'not_started', nodes: [], issues: [] })
const versions = ref<Record<string, Artifact[]>>({})
const selected = ref<Record<string, string>>({})
const kind = ref<'teacher' | 'student'>('teacher')
const job = ref<ExportJob>()
const filename = ref('')
const loading = ref(true)
const working = ref(false)
const error = ref<ApiError>()
let timer: number | undefined
const labels: Record<ArtifactType, string> = { lesson_plan: '教学设计', slide_deck: '课件', speaker_notes: '逐页讲稿', exercise_set: '练习' }
const requiredTypes = computed<ArtifactType[]>(() => kind.value === 'teacher' ? ['lesson_plan','slide_deck','speaker_notes','exercise_set'] : ['slide_deck','exercise_set'])
const exporting = computed(() => !!job.value && ['pending','running'].includes(job.value.status))
const canStart = computed(() => canExport(graph.value.status) && !exporting.value && requiredTypes.value.every((type) => selected.value[type]))

async function load() {
  loading.value = true
  try {
    const [graphRow, artifacts] = await Promise.all([api.graph(projectId), api.artifacts(projectId)])
    graph.value = graphRow
    const rows = await Promise.all(artifacts.map((item) => api.versions(item.artifact_id)))
    artifacts.forEach((item, index) => {
      versions.value[item.type] = rows[index]
      selected.value[item.type] ||= rows[index][0]?.version_id || ''
    })
  } catch (requestError) { error.value = requestError as ApiError }
  finally { loading.value = false }
}

async function poll() {
  if (!job.value) return
  try {
    job.value = await api.exportStatus(job.value.job_id)
    if (!['succeeded','failed'].includes(job.value.status)) timer = window.setTimeout(poll, 1000)
  } catch (requestError) { error.value = requestError as ApiError }
}

async function start() {
  if (working.value || !canStart.value) return
  working.value = true
  error.value = undefined
  try {
    const versionIds = requiredTypes.value.map((type) => selected.value[type]).filter(Boolean)
    job.value = await api.createExport(projectId, kind.value, versionIds)
    await poll()
  } catch (requestError) { error.value = requestError as ApiError }
  finally { working.value = false }
}

async function download() {
  if (!job.value || working.value) return
  working.value = true
  try {
    const file = await api.downloadExport(job.value.job_id)
    const url = URL.createObjectURL(file.blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file.filename
    link.click()
    URL.revokeObjectURL(url)
    filename.value = file.filename
    ElMessage.success('下载已开始')
  } catch (requestError) { error.value = requestError as ApiError }
  finally { working.value = false }
}

onMounted(load)
onUnmounted(() => clearTimeout(timer))
</script>

<template>
  <section>
    <div class="page-head"><div><h2>导出备课成果</h2><p>选择真实产物版本，教师确认后生成安全 ZIP 包。</p></div><el-button @click="router.push(`/quality/${projectId}`)">返回质量检查</el-button></div>
    <AppLoading v-if="loading" />
    <AppError v-else-if="error && !Object.keys(versions).length" :error="error.message" @retry="load" />
    <div v-else class="panel panel-pad">
      <el-alert v-if="!canExport(graph.status)" type="warning" :closable="false" title="流程尚未由教师确认，暂不能导出。" />
      <div class="export-choice">
        <article :class="['choice',{active:kind === 'teacher'}]" @click="kind = 'teacher'"><el-tag>教师使用</el-tag><h2>教师备课包</h2><p>教学设计、课件、逐页讲稿、含答案练习与引用。</p></article>
        <article :class="['choice',{active:kind === 'student'}]" @click="kind = 'student'"><el-tag type="success">学生使用</el-tag><h2>学生练习包</h2><p>仅含课件与无答案练习，不包含讲稿和解析。</p></article>
      </div>

      <h3>选择产物版本</h3>
      <div v-for="type in requiredTypes" :key="type" class="version-select"><span>{{ labels[type] }}</span><el-select v-model="selected[type]" placeholder="请选择版本"><el-option v-for="item in versions[type] || []" :key="item.version_id" :label="`v${item.version_no} · ${item.change_type} · ${new Date(item.created_at).toLocaleString()}`" :value="item.version_id" /></el-select></div>
      <div class="version-select"><span>导出格式</span><el-input model-value="ZIP" disabled /></div>
      <el-alert v-if="kind === 'student'" type="success" :closable="false" title="学生包预览：已隐藏逐页讲稿、答案和解析。" />
      <el-alert v-if="error" type="error" :closable="false" :title="error.message" />

      <div v-if="job" class="job-state"><StatusTag :status="job.status" /><el-progress :percentage="exportProgress(job.status)" /><span v-if="job.error_message" class="task-error">{{ job.error_message }}</span><span v-if="filename">已下载：{{ filename }}</span></div>
      <el-button type="primary" size="large" :loading="working || exporting" :disabled="working || !canStart" @click="start">{{ job?.status === 'failed' ? '重试导出' : `生成${kind === 'teacher' ? '教师' : '学生'}包` }}</el-button>
      <el-button v-if="job?.status === 'succeeded'" type="success" size="large" :loading="working" @click="download">下载 {{ kind === 'teacher' ? '教师' : '学生' }} ZIP 包</el-button>
    </div>
  </section>
</template>

<style scoped>
.version-select{display:grid;grid-template-columns:110px minmax(240px,420px);align-items:center;gap:12px;margin:12px 0}.job-state{display:grid;gap:8px;margin:18px 0;max-width:540px}.task-error{color:#d84c4c;overflow-wrap:anywhere}
</style>
