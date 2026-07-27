<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ArrowLeft, RefreshRight } from '@element-plus/icons-vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { api } from '../api'
import { sourcesApi } from '../api/sources'
import { knowledgeBasesApi } from '../api/knowledgeBases'
import type { Project, Source, Task } from '../types'
import {
  beginGenerationSession,
  clearGenerationSession,
  getGenerationSession,
  updateGenerationSession,
  type GenerationSession,
} from '../services/generationSession'
import { taskErrorText, workbenchPath } from '../utils/workbench'
import { useProjectStore } from '../stores/project'

const router = useRouter()
const projectStore = useProjectStore()
const session = ref<GenerationSession>()
const project = ref<Project>()
const task = ref<Task>()
const stage = ref('正在进入安全生成流程')
const localProgress = ref(3)
const phase = ref(0)
const locked = ref(true)
const failure = ref('')
const elapsedSeconds = ref(0)
let stopped = false
let elapsedTimer: number | undefined

const progress = computed(() => {
  if (!task.value) return localProgress.value
  return Math.min(96, Math.max(38, 38 + Math.round(task.value.progress * 0.58)))
})
const elapsed = computed(() => {
  const minutes = Math.floor(elapsedSeconds.value / 60)
  const seconds = elapsedSeconds.value % 60
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
})
const phases = ['准备主题与资料', '生成内容与版式', '完成演示']

function sleep(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

async function uploadSources(current: GenerationSession, projectId: string) {
  let uploadedIds = [...current.uploadedSourceIds]

  if (uploadedIds.length < current.expectedFileCount && current.files.length) {
    for (let index = uploadedIds.length; index < current.files.length; index += 1) {
      const file = current.files[index]
      stage.value = `正在上传资料 ${index + 1}/${current.files.length}`
      const source = await sourcesApi.upload(projectId, file, (value) => {
        localProgress.value = 12 + Math.round(((index + value / 100) / current.files.length) * 16)
      })
      uploadedIds.push(source.id)
      updateGenerationSession({ uploadedSourceIds: uploadedIds })
    }
  }

  if (uploadedIds.length < current.expectedFileCount) {
    throw new Error('页面刷新时仍有本地资料尚未上传，请返回重新选择资料')
  }

  if (!uploadedIds.length) return []
  stage.value = '正在解析资料并建立知识索引'
  localProgress.value = 30
  for (let attempt = 0; attempt < 180 && !stopped; attempt += 1) {
    const selected = await Promise.all(uploadedIds.map((id) => knowledgeBasesApi.source(id)))
    const failed = selected.find((item) => item.status === 'failed')
    if (failed) throw new Error(`${failed.original_name} 处理失败：${failed.error_message || '无法建立索引'}`)
    if (selected.length === uploadedIds.length && selected.every((item: Source) => item.status === 'ready')) {
      return selected.map((item) => item.id)
    }
    localProgress.value = Math.min(36, 30 + Math.floor(attempt / 15))
    await sleep(1000)
  }
  throw new Error('资料处理超时，请返回后重新生成')
}

async function pollTask(taskId: string) {
  phase.value = 1
  while (!stopped) {
    const currentTask = await api.task(taskId)
    task.value = currentTask
    stage.value = currentTask.stage || 'AI 正在组织内容与版式'
    if (currentTask.status === 'succeeded') {
      phase.value = 2
      localProgress.value = 100
      stage.value = '演示生成完成，正在进入编辑器'
      clearGenerationSession()
      locked.value = false
      await sleep(450)
      await router.replace(workbenchPath(currentTask.project_id))
      return
    }
    if (currentTask.status === 'failed' || currentTask.status === 'cancelled') {
      throw new Error(taskErrorText(currentTask.error_code, currentTask.error_message))
    }
    await sleep(1200)
  }
}

async function runGeneration() {
  failure.value = ''
  locked.value = true
  const current = getGenerationSession()
  session.value = current
  if (!current) {
    locked.value = false
    failure.value = '没有找到正在进行的生成任务'
    return
  }

  try {
    let projectId = current.projectId
    if (!projectId) {
      if (!current.form) throw new Error('缺少创建演示所需的信息')
      stage.value = '正在创建演示并准备所选主题'
      localProgress.value = 7
      project.value = await api.createProject(current.form)
      projectId = project.value.id
      projectStore.select(projectId)
      session.value = updateGenerationSession({ projectId })
    } else {
      project.value = await api.project(projectId)
      projectStore.select(projectId)
    }

    if (current.taskId) {
      await pollTask(current.taskId)
      return
    }

    const existingTasks = await api.tasks(projectId)
    const activeTask = existingTasks.find((item) => item.status === 'pending' || item.status === 'running')
    if (activeTask) {
      task.value = activeTask
      updateGenerationSession({ taskId: activeTask.id })
      await pollTask(activeTask.id)
      return
    }

    phase.value = 0
    const uploadedIds = await uploadSources(getGenerationSession() || current, projectId)
    const selectedSourceIds = [...new Set([...current.sourceIds, ...uploadedIds])]
    const selectedKnowledgeBaseIds = [...new Set([
      ...(current.knowledgeBaseIds || project.value?.knowledge_base_ids || []),
      ...(uploadedIds.length ? ['personal'] : []),
    ])]
    stage.value = '正在启动 AI 生成引擎'
    localProgress.value = 37
    const createdTask = await api.createTask(projectId, {
      type: 'full_lesson',
      selected_source_ids: selectedSourceIds,
      selected_knowledge_base_ids: selectedKnowledgeBaseIds,
      teacher_requirements: current.prompt,
      idempotency_key: current.idempotencyKey,
    })
    task.value = createdTask
    updateGenerationSession({ taskId: createdTask.id, uploadedSourceIds: uploadedIds })
    await pollTask(createdTask.id)
  } catch (requestError) {
    clearGenerationSession()
    locked.value = false
    failure.value = (requestError as Error).message
  }
}

async function retry() {
  if (!project.value || !task.value) return returnToEdit()
  const restored = beginGenerationSession({
    mode: 'regenerate',
    projectId: project.value.id,
    prompt: project.value.teacher_requirements,
    sourceIds: session.value?.sourceIds || [],
    knowledgeBaseIds: project.value.knowledge_base_ids,
  })
  restored.taskId = task.value.id
  updateGenerationSession({ taskId: task.value.id })
  failure.value = ''
  locked.value = true
  try {
    task.value = await api.retryTask(task.value.id)
    updateGenerationSession({ taskId: task.value.id })
    await pollTask(task.value.id)
  } catch (requestError) {
    clearGenerationSession()
    locked.value = false
    failure.value = (requestError as Error).message
  }
}

async function returnToEdit() {
  clearGenerationSession()
  locked.value = false
  if (project.value) await router.replace({ path: '/create', query: { edit: project.value.id } })
  else await router.replace('/create')
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!locked.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => !locked.value)
onMounted(() => {
  elapsedTimer = window.setInterval(() => (elapsedSeconds.value += 1), 1000)
  window.addEventListener('beforeunload', handleBeforeUnload)
  runGeneration()
})
onUnmounted(() => {
  stopped = true
  clearInterval(elapsedTimer)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<template>
  <main class="generation-page">
    <div class="generation-noise" />
    <section class="generation-panel" aria-live="polite">
      <div class="generation-brand">
        <span class="mini-brand"><i /><i /><i /></span>
        <b>Any2PPT</b>
      </div>

      <template v-if="!failure">
        <div class="generation-orbit">
          <span>✦</span>
          <i /><i /><i />
        </div>
        <span class="generation-eyebrow">AI + SLIDEV · LOCKED WORKFLOW</span>
        <h1>正在生成你的演示</h1>
        <p>{{ stage }}</p>

        <div class="generation-progress">
          <div><span>{{ project?.name || '正在准备项目' }}</span><b>{{ progress }}%</b></div>
          <el-progress :percentage="progress" :show-text="false" :stroke-width="8" />
        </div>

        <ol class="generation-phases">
          <li v-for="(item, index) in phases" :key="item" :class="{ active: index === phase, done: index < phase }">
            <span>{{ index < phase ? '✓' : index + 1 }}</span>
            <b>{{ item }}</b>
          </li>
        </ol>

        <div class="generation-lock-note">
          <span>🔒</span>
          <p><b>生成期间已锁定操作</b><small>完成后会自动进入编辑器，请不要关闭或刷新页面 · {{ elapsed }}</small></p>
        </div>
      </template>

      <template v-else>
        <div class="generation-failed">!</div>
        <span class="generation-eyebrow">GENERATION INTERRUPTED</span>
        <h1>这次生成没有完成</h1>
        <p>{{ failure }}</p>
        <div class="generation-error-actions">
          <el-button v-if="task" type="primary" size="large" :icon="RefreshRight" @click="retry">重新生成</el-button>
          <el-button size="large" :icon="ArrowLeft" @click="returnToEdit">返回修改</el-button>
        </div>
      </template>
    </section>
  </main>
</template>

<style scoped>
.generation-page{position:relative;min-width:720px;height:100vh;display:grid;place-items:center;overflow:hidden;background:#f3f7f4;color:#17221d}.generation-page:before,.generation-page:after{content:"";position:absolute;border-radius:50%;filter:blur(4px)}.generation-page:before{width:520px;height:520px;left:-170px;top:-210px;background:radial-gradient(circle,rgba(89,218,169,.22),transparent 68%)}.generation-page:after{width:600px;height:600px;right:-210px;bottom:-280px;background:radial-gradient(circle,rgba(44,142,226,.12),transparent 68%)}.generation-noise{position:absolute;inset:0;opacity:.26;background-image:linear-gradient(rgba(17,87,63,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(17,87,63,.045) 1px,transparent 1px);background-size:58px 58px}.generation-panel{position:relative;z-index:1;width:min(720px,calc(100vw - 80px));padding:42px 64px 38px;border:1px solid rgba(200,215,206,.86);border-radius:28px;background:rgba(255,255,255,.9);box-shadow:0 28px 90px rgba(35,67,52,.12);text-align:center;backdrop-filter:blur(18px)}.generation-brand{position:absolute;left:28px;top:25px;display:flex;align-items:center;gap:9px;font-size:14px}.mini-brand{width:30px;height:30px;display:flex;align-items:end;justify-content:center;gap:2px;padding:7px;border-radius:9px;background:#0eaa79}.mini-brand i{width:3px;border-radius:2px;background:white}.mini-brand i:nth-child(1){height:7px}.mini-brand i:nth-child(2){height:14px}.mini-brand i:nth-child(3){height:10px}.generation-orbit{position:relative;width:112px;height:112px;display:grid;place-items:center;margin:28px auto 20px;border-radius:50%;background:radial-gradient(circle,#d7f8eb 12%,#edf9f4 56%,transparent 58%)}.generation-orbit:before{content:"";position:absolute;inset:5px;border:1px solid #b4e6d2;border-radius:50%;animation:spin 8s linear infinite}.generation-orbit>span{width:56px;height:56px;display:grid;place-items:center;border-radius:17px;background:#0eaa79;color:white;font-size:25px;box-shadow:0 14px 30px rgba(14,170,121,.28);animation:pulse 2s ease-in-out infinite}.generation-orbit>i{position:absolute;width:9px;height:9px;border:2px solid white;border-radius:50%;background:#0eaa79;box-shadow:0 2px 8px rgba(14,170,121,.3)}.generation-orbit>i:nth-of-type(1){top:10px;left:25px}.generation-orbit>i:nth-of-type(2){right:4px;bottom:35px}.generation-orbit>i:nth-of-type(3){left:9px;bottom:18px}.generation-eyebrow{color:#0b9168;font-size:10px;font-weight:800;letter-spacing:1.8px}.generation-panel h1{margin:11px 0 8px;font-family:"Songti SC","Noto Serif SC",serif;font-size:38px;font-weight:600}.generation-panel>p{margin:0;color:#748078;font-size:14px}.generation-progress{margin:30px auto 0;text-align:left}.generation-progress>div{display:flex;justify-content:space-between;margin-bottom:10px;color:#6b776f;font-size:11px}.generation-progress b{color:#0b9168;font-size:13px}.generation-progress :deep(.el-progress-bar__outer){background:#e8efeb}.generation-progress :deep(.el-progress-bar__inner){background:linear-gradient(90deg,#0eaa79,#65d7ad)}.generation-phases{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin:24px 0 0;padding:0;list-style:none}.generation-phases li{position:relative;display:grid;justify-items:center;gap:7px;color:#a2aaa5;font-size:10px}.generation-phases li:not(:last-child):after{content:"";position:absolute;z-index:-1;left:58%;top:14px;width:84%;height:1px;background:#dce5df}.generation-phases span{width:28px;height:28px;display:grid;place-items:center;border:1px solid #d8e1dc;border-radius:50%;background:#fff}.generation-phases li.active,.generation-phases li.done{color:#0b9168}.generation-phases li.active span{border-color:#0eaa79;box-shadow:0 0 0 5px #e8f8f1}.generation-phases li.done span{border-color:#0eaa79;background:#0eaa79;color:#fff}.generation-lock-note{display:flex;align-items:center;justify-content:center;gap:10px;margin-top:26px;padding:13px;border-radius:12px;background:#f4f7f5;color:#67736c;text-align:left}.generation-lock-note>span{font-size:18px}.generation-lock-note p{display:grid;margin:0}.generation-lock-note b{font-size:11px}.generation-lock-note small{margin-top:2px;color:#929b96;font-size:9px}.generation-failed{width:72px;height:72px;display:grid;place-items:center;margin:35px auto 22px;border-radius:22px;background:#fff1ee;color:#d85b49;font:700 32px serif}.generation-error-actions{display:flex;justify-content:center;gap:10px;margin-top:28px}.generation-error-actions :deep(.el-button--primary){--el-button-bg-color:#0eaa79;--el-button-border-color:#0eaa79}@keyframes spin{to{transform:rotate(360deg)}}@keyframes pulse{50%{transform:scale(1.05);box-shadow:0 18px 38px rgba(14,170,121,.34)}}@media(max-width:760px){.generation-page{min-width:0}.generation-panel{width:calc(100vw - 28px);padding:70px 24px 30px}.generation-panel h1{font-size:30px}.generation-phases b{font-size:9px}}
</style>
