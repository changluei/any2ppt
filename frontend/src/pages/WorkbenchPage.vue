<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowLeft, Download, MagicStick, Paperclip } from '@element-plus/icons-vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { sourcesApi } from '../api/sources'
import { imagesApi } from '../api/images'
import type { ApiError, Artifact, ExportJob, GraphState, Project, Source, Task, ThemeDescriptor } from '../types'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import SlidevPreview from '../components/SlidevPreview.vue'
import { beginGenerationSession, clearGenerationSession } from '../services/generationSession'
import { useProjectStore } from '../stores/project'
import { generationPath, shouldPoll, taskErrorText } from '../utils/workbench'

const route = useRoute()
const router = useRouter()
const projectId = String(route.params.projectId)
useProjectStore().select(projectId)
const project = ref<Project>()
const themes = ref<ThemeDescriptor[]>([])
const sources = ref<Source[]>([])
const tasks = ref<Task[]>([])
const artifacts = ref<Artifact[]>([])
const versions = ref<Artifact[]>([])
const selectedSourceIds = ref<string[]>([])
const selectedVersionId = ref('')
const selectedSlideId = ref('')
const requirements = ref('')
const loading = ref(true)
const busy = ref('')
const error = ref<ApiError>()
const markdownDirty = ref(false)
const markdownSaving = ref(false)
const exportJob = ref<ExportJob>()
const chatInput = ref('')
const chatImage = ref<File>()
const chatImagePreview = ref('')
const chatUploadProgress = ref(0)
const chatThread = ref<HTMLElement>()
type ChatMessage = { id: string; role: 'assistant' | 'user'; text: string; imageName?: string }
const chatMessages = ref<ChatMessage[]>([])
let timer: number | undefined
let markdownAutosaveTimer: number | undefined
let markdownRevision = 0
let markdownSavePromise: Promise<void> | undefined
let queuedSlideId = ''
type PendingMarkdown = { slideId: string; markdown: string; revision: number }
let pendingMarkdown: PendingMarkdown | undefined

const readySources = computed(() => sources.value.filter((item) => item.status === 'ready'))
const projectTheme = computed(() => themes.value.find((item) => item.id === project.value?.theme_id))
const latestTask = computed(() => tasks.value[0])
const generating = computed(() => shouldPoll(tasks.value))
const latestDeck = computed(() => artifacts.value.find((item) => item.type === 'slide_deck'))
const deck = computed(() => versions.value.find((item) => item.version_id === selectedVersionId.value) || latestDeck.value)
const slides = computed(() => deck.value?.content.slides || [])
const selectedSlide = computed(() => slides.value.find((item) => item.slide_id === selectedSlideId.value) || slides.value[0])
const canGenerate = computed(() => !generating.value)
const currentImages = computed(() => selectedSlide.value?.images || [])
const placementOptions = [
  { value: 'left', label: '左侧' },
  { value: 'right', label: '右侧' },
  { value: 'center', label: '居中' },
  { value: 'wide', label: '下方宽图' },
  { value: 'background', label: '背景图' },
] as const

function schedule() {
  clearTimeout(timer)
  if (generating.value) timer = window.setTimeout(refresh, 1200)
}

async function loadVersions() {
  if (!latestDeck.value) {
    versions.value = []
    selectedVersionId.value = ''
    return
  }
  versions.value = await api.versions(latestDeck.value.artifact_id)
  selectedVersionId.value ||= latestDeck.value.version_id
}

async function load() {
  loading.value = true
  error.value = undefined
  try {
    ;[project.value, sources.value, tasks.value, artifacts.value, themes.value] = await Promise.all([
      api.project(projectId),
      sourcesApi.list(projectId),
      api.tasks(projectId),
      api.artifacts(projectId),
      api.themes(),
    ])
    requirements.value = project.value.teacher_requirements
    selectedSourceIds.value = readySources.value.map((item) => item.id)
    await loadVersions()
    selectedSlideId.value = slides.value[0]?.slide_id || ''
    if (!chatMessages.value.length) {
      chatMessages.value.push({
        id: crypto.randomUUID(),
        role: 'assistant',
        text: project.value.knowledge_base_ids.length || readySources.value.length
          ? `我已经连接 ${project.value.knowledge_base_ids.length} 个知识库${readySources.value.length ? `和本次上传的 ${readySources.value.length} 份资料` : ''}。你可以直接告诉我修改哪一页，也可以附一张图片让我放进指定页面。`
          : '这份演示生成时没有连接知识库，因此内容主要来自你的描述。你可以继续让我修改页面，或附一张图片让我放进指定页面。',
      })
    }
    schedule()
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    loading.value = false
  }
}

async function refresh() {
  try {
    ;[tasks.value, artifacts.value] = await Promise.all([api.tasks(projectId), api.artifacts(projectId)])
    if (!generating.value) {
      await loadVersions()
      selectedSlideId.value ||= slides.value[0]?.slide_id || ''
    }
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    schedule()
  }
}

async function generatePpt() {
  if (!canGenerate.value || busy.value) return
  busy.value = 'generate'
  error.value = undefined
  try {
    beginGenerationSession({
      mode: 'regenerate',
      projectId,
      prompt: requirements.value,
      sourceIds: selectedSourceIds.value,
      knowledgeBaseIds: project.value?.knowledge_base_ids || [],
    })
    await router.push(generationPath)
  } catch (requestError) {
    clearGenerationSession()
    error.value = requestError as ApiError
  } finally {
    busy.value = ''
  }
}

async function waitForGraph(): Promise<GraphState> {
  let graph = await api.graph(projectId)
  if (graph.status === 'not_started') {
    const task = tasks.value.find((item) => item.type === 'full_lesson' && item.status === 'succeeded')
    graph = await api.startGraph(projectId, task?.id)
  }
  let resumed = false
  for (let index = 0; index < 80; index += 1) {
    if (graph.status === 'succeeded') return graph
    if (graph.status === 'failed' || graph.status === 'cancelled') {
      if (!graph.id || resumed) break
      graph = await api.resumeGraph(graph.id)
      resumed = true
      continue
    }
    if (graph.status === 'awaiting_confirmation' || graph.status === 'needs_revision') {
      if (!graph.id) break
      const hasBlockingIssue = graph.issues.some((item) => item.severity === 'fail')
      if (hasBlockingIssue && (graph.attempt || 1) < 3) {
        await api.confirmGraph(graph.id, 'revise')
      } else if (hasBlockingIssue) {
        throw new Error('PPT 自动检查未通过，请重新生成后再试')
      } else {
        await api.confirmGraph(graph.id, 'accept')
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 300))
    graph = await api.graph(projectId)
  }
  return graph
}

async function downloadPpt() {
  if (!deck.value || busy.value) return
  busy.value = 'export'
  error.value = undefined
  try {
    const graph = await waitForGraph()
    if (graph.status !== 'succeeded') throw new Error('PPT 尚未准备完成，请稍后重试')
    exportJob.value = await api.createExport(projectId, 'pptx', [deck.value.version_id])
    ElMessage.info('正在使用项目模板渲染 PPT，首次导出可能需要约一分钟')
    for (let index = 0; index < 360; index += 1) {
      exportJob.value = await api.exportStatus(exportJob.value.job_id)
      if (['succeeded', 'failed'].includes(exportJob.value.status)) break
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
    if (exportJob.value.status !== 'succeeded') throw new Error(exportJob.value.error_message || 'PPT 导出失败')
    const file = await api.downloadExport(exportJob.value.job_id)
    const url = URL.createObjectURL(file.blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file.filename || `${project.value?.lesson_topic || '备课课件'}.pptx`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('PPT 已生成')
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    busy.value = ''
  }
}

function updateArtifact(changed: Artifact) {
  artifacts.value = artifacts.value.map((item) => item.artifact_id === changed.artifact_id ? changed : item)
  versions.value = [changed, ...versions.value.filter((item) => item.version_id !== changed.version_id)]
  selectedVersionId.value = changed.version_id
}

function changeMarkdown(markdown: string) {
  const slide = selectedSlide.value
  if (!slide) return
  clearTimeout(markdownAutosaveTimer)
  const revision = ++markdownRevision
  pendingMarkdown = { slideId: slide.slide_id, markdown, revision }
  markdownDirty.value = markdown.trim() !== slide.markdown.trim()
  if (!markdownDirty.value) {
    pendingMarkdown = undefined
    return
  }
  if (!markdown.trim()) return
  markdownAutosaveTimer = window.setTimeout(() => void flushMarkdownAutosave(), 650)
}

async function flushMarkdownAutosave(): Promise<void> {
  clearTimeout(markdownAutosaveTimer)
  if (markdownSavePromise) return markdownSavePromise
  const edit = pendingMarkdown
  const currentDeck = latestDeck.value
  if (!edit || !edit.markdown.trim() || !currentDeck) return

  markdownSaving.value = true
  error.value = undefined
  markdownSavePromise = (async () => {
    try {
      const changed = await api.saveSlideMarkdown(currentDeck.artifact_id, {
        base_version_no: currentDeck.version_no,
        slide_id: edit.slideId,
        markdown: edit.markdown,
      })
      updateArtifact(changed)
      if (pendingMarkdown?.revision === edit.revision) {
        pendingMarkdown = undefined
        markdownDirty.value = false
      } else if (pendingMarkdown) {
        const savedSlide = changed.content.slides?.find((item) => item.slide_id === pendingMarkdown?.slideId)
        markdownDirty.value = pendingMarkdown.markdown.trim() !== savedSlide?.markdown.trim()
      }
    } catch (requestError) {
      error.value = requestError as ApiError
      markdownDirty.value = true
    } finally {
      markdownSaving.value = false
      markdownSavePromise = undefined
      if (pendingMarkdown && pendingMarkdown.revision !== edit.revision && pendingMarkdown.markdown.trim()) {
        markdownAutosaveTimer = window.setTimeout(() => void flushMarkdownAutosave(), 80)
      } else if (!markdownDirty.value && queuedSlideId) {
        selectedSlideId.value = queuedSlideId
        queuedSlideId = ''
      }
    }
  })()
  return markdownSavePromise
}

function clearChatImage() {
  if (chatImagePreview.value) URL.revokeObjectURL(chatImagePreview.value)
  chatImage.value = undefined
  chatImagePreview.value = ''
  chatUploadProgress.value = 0
}

function pickChatImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const suffix = file.name.split('.').pop()?.toLowerCase()
  if (!['png', 'jpg', 'jpeg', 'webp'].includes(suffix || '')) {
    ElMessage.warning('请选择 PNG、JPG、JPEG 或 WEBP 图片')
    return
  }
  clearChatImage()
  chatImage.value = file
  chatImagePreview.value = URL.createObjectURL(file)
}

function targetSlideFor(message: string) {
  const order = Number(/第\s*(\d+)\s*(?:页|张)/.exec(message)?.[1] || 0)
  return slides.value.find((item) => item.order === order) || selectedSlide.value
}

function imagePositionFor(message: string) {
  if (/背景|铺满/.test(message)) return 'background'
  if (/左侧|左边/.test(message)) return 'left'
  if (/居中|中央|中间/.test(message)) return 'center'
  if (/宽图|横幅|底部|下方/.test(message)) return 'wide'
  return 'right'
}

function isGreeting(message: string) {
  return /^(你好|您好|在吗|谢谢|谢谢你|你能做什么)[？?！!。,\s]*$/.test(message)
}

function isImageOnlyInstruction(message: string, hasImage: boolean) {
  return hasImage
    && /(添加|放到|放在|放进|放入|插入|使用|这张|图片)/.test(message)
    && !/(精简|扩写|重写|改写|调整文字|修改标题|补充内容|改成)/.test(message)
}

async function scrollChat() {
  await nextTick()
  chatThread.value?.scrollTo({ top: chatThread.value.scrollHeight, behavior: 'smooth' })
}

async function sendChat() {
  const message = chatInput.value.trim()
  const imageFile = chatImage.value
  if (
    (!message && !imageFile)
    || busy.value
    || markdownDirty.value
    || markdownSaving.value
    || !latestDeck.value
  ) return
  const target = targetSlideFor(message)
  if (!target) return

  chatMessages.value.push({
    id: crypto.randomUUID(),
    role: 'user',
    text: message || `把这张图片添加到第 ${target.order} 页`,
    imageName: imageFile?.name,
  })
  chatInput.value = ''
  clearChatImage()
  await scrollChat()

  busy.value = 'chat'
  let working = latestDeck.value
  const completed: string[] = []
  try {
    if (imageFile) {
      const uploaded = await imagesApi.upload(projectId, imageFile, (value) => (chatUploadProgress.value = value))
      const changed = await api.placeSlideImage(working.artifact_id, {
        base_version_no: working.version_no,
        slide_id: target.slide_id,
        image_id: uploaded.id,
        position: imagePositionFor(message),
        caption: '',
      })
      updateArtifact(changed)
      working = changed
      completed.push(`图片已经添加到第 ${target.order} 页`)
    }

    if (message && !isGreeting(message) && !isImageOnlyInstruction(message, Boolean(imageFile))) {
      const changed = await api.revise(working.artifact_id, {
        base_version_no: working.version_no,
        target_type: 'slide',
        target_id: target.slide_id,
        instruction: message,
        sync_related: true,
      })
      updateArtifact(changed)
      working = changed
      completed.push(`第 ${target.order} 页已按要求更新`)
    }

    await loadVersions()
    chatMessages.value.push({
      id: crypto.randomUUID(),
      role: 'assistant',
      text: completed.length
        ? `${completed.join('，')}。修改已保存为新版本。`
        : '你好！你可以让我修改当前页，也可以说“把这张图放到第 3 页右侧”并附上图片。',
    })
  } catch (requestError) {
    chatMessages.value.push({
      id: crypto.randomUUID(),
      role: 'assistant',
      text: `这次没有完成：${(requestError as Error).message}。你可以换一种更具体的说法再试一次。`,
    })
  } finally {
    busy.value = ''
    chatUploadProgress.value = 0
    await scrollChat()
  }
}

async function removeImage(placementId: string) {
  if (!latestDeck.value || busy.value) return
  busy.value = 'image'
  try {
    const changed = await api.removeSlideImage(
      latestDeck.value.artifact_id,
      placementId,
      latestDeck.value.version_no,
    )
    artifacts.value = artifacts.value.map((item) => item.artifact_id === changed.artifact_id ? changed : item)
    selectedVersionId.value = changed.version_id
    await loadVersions()
    ElMessage.success('图片已从当前页移除')
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    busy.value = ''
  }
}

function selectSlide(slideId: string) {
  if (markdownDirty.value || markdownSaving.value) {
    queuedSlideId = slideId
    void flushMarkdownAutosave()
    return
  }
  selectedSlideId.value = slideId
}

watch(deck, () => {
  if (!slides.value.some((item) => item.slide_id === selectedSlideId.value)) {
    selectedSlideId.value = slides.value[0]?.slide_id || ''
  }
})
async function confirmLeave() {
  if (generating.value) {
    ElMessage.warning('PPT 正在生成，完成前不能离开当前页面')
    return false
  }
  if (!markdownDirty.value && !markdownSaving.value) return true
  await flushMarkdownAutosave()
  return !markdownDirty.value || window.confirm('自动同步尚未完成，确定离开吗？')
}
function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!markdownDirty.value && !markdownSaving.value && !generating.value) return
  event.preventDefault()
  event.returnValue = ''
}
onBeforeRouteLeave(confirmLeave)
onMounted(load)
onMounted(() => window.addEventListener('beforeunload', handleBeforeUnload))
onUnmounted(() => {
  clearTimeout(timer)
  clearTimeout(markdownAutosaveTimer)
  clearChatImage()
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<template>
  <AppLoading v-if="loading" />
  <AppError v-else-if="error && !project" :error="error.message" @retry="load" />
  <section v-else-if="project" class="editor-app">
    <div v-if="generating" class="workbench-generation-lock" aria-live="polite">
      <div class="lock-orbit">✦</div>
      <span>AI + SLIDEV · LOCKED WORKFLOW</span>
      <h1>正在生成你的演示</h1>
      <p>{{ latestTask?.stage || '正在组织内容与版式' }}</p>
      <div class="lock-progress">
        <b>{{ latestTask?.progress || 0 }}%</b>
        <el-progress :percentage="latestTask?.progress || 0" :show-text="false" :stroke-width="8" />
      </div>
      <small>生成期间已锁定所有操作，完成后会自动恢复编辑</small>
    </div>
    <header class="editor-topbar">
      <div class="editor-brand">
        <button type="button" aria-label="返回我的演示" @click="router.push('/projects')"><el-icon><ArrowLeft /></el-icon></button>
        <span class="mini-brand"><i /><i /><i /></span>
        <div>
          <b>Any2PPT</b>
          <small>{{ project.grade }} · {{ project.subject }}</small>
        </div>
      </div>
      <div class="editor-title">
        <b>{{ project.name }}</b>
        <span v-if="markdownSaving">正在自动同步</span>
        <span v-else-if="markdownDirty">等待自动同步</span>
        <span v-else>已自动同步</span>
      </div>
      <div class="editor-actions">
        <el-select v-if="versions.length > 1" v-model="selectedVersionId" size="small" :disabled="markdownDirty || markdownSaving">
          <el-option v-for="item in versions" :key="item.version_id" :label="`版本 ${item.version_no}`" :value="item.version_id" />
        </el-select>
        <el-button
          type="primary"
          :icon="MagicStick"
          :loading="generating || busy === 'generate'"
          :disabled="!canGenerate || !!busy || markdownDirty || markdownSaving"
          @click="generatePpt"
        >
          {{ latestDeck ? '重新生成' : '生成 PPT' }}
        </el-button>
        <el-button
          :icon="Download"
          :loading="busy === 'export'"
          :disabled="!deck || generating || !!busy || markdownDirty || markdownSaving"
          @click="downloadPpt"
        >
          导出
        </el-button>
      </div>
    </header>

    <div class="editor-body">
      <aside class="slides-sidebar">
        <button type="button" class="add-slide" disabled aria-label="新增页面">＋</button>
        <nav aria-label="PPT 页面">
          <button
            v-for="slide in slides"
            :key="slide.slide_id"
            type="button"
            class="slide-thumb"
            :class="{ active: selectedSlide?.slide_id === slide.slide_id }"
            @click="selectSlide(slide.slide_id)"
          >
            <span>{{ slide.order }}</span>
            <div :style="{ background: deck?.content.theme_palette?.background, color: deck?.content.theme_palette?.text }">
              <i :style="{ background: deck?.content.theme_palette?.accent }" />
              <b>{{ slide.title }}</b>
              <small>{{ slide.teaching_stage || '课件页面' }}</small>
            </div>
          </button>
          <div v-if="!slides.length" class="slide-placeholder">
            <span>1</span>
            <div>等待生成</div>
          </div>
        </nav>
      </aside>

      <main class="editor-main">
        <el-alert v-if="error" type="error" :closable="true" class="workbench-alert" @close="error = undefined">
          <template #title>{{ taskErrorText(error.code, error.message) }}</template>
        </el-alert>

        <template v-if="deck && slides.length">
          <div class="canvas-heading">
            <div>
              <span>{{ selectedSlide?.order?.toString().padStart(2, '0') }} / {{ slides.length.toString().padStart(2, '0') }}</span>
              <b>{{ selectedSlide?.title }}</b>
            </div>
            <div>
              <el-tag effect="plain">{{ deck.content.theme_name || projectTheme?.name || project.theme_id }}</el-tag>
            </div>
          </div>
          <SlidevPreview
            :key="selectedSlide?.slide_id"
            :title="selectedSlide?.title"
            :markdown="selectedSlide?.markdown || ''"
            :images="selectedSlide?.images || []"
            :image-base-url="imagesApi.baseUrl()"
            :theme-palette="deck.content.theme_palette || projectTheme?.palette"
            :rendered-preview-url="selectedSlide ? api.previewUrl(deck.artifact_id, selectedSlide.slide_id, deck.version_no) : ''"
            :syncing="markdownSaving"
            @change="changeMarkdown"
          />
          <div v-if="currentImages.length" class="current-images">
            <span>本页图片</span>
            <el-tag
              v-for="image in currentImages"
              :key="image.placement_id"
              closable
              :disable-transitions="true"
              @close="removeImage(image.placement_id)"
            >
              {{ image.original_name }} · {{ placementOptions.find(item => item.value === image.position)?.label }}
            </el-tag>
          </div>
        </template>

        <div v-else class="deck-empty">
          <div class="empty-orbit"><span>&lt;/&gt;</span></div>
          <span class="section-number">AI + SLIDEV</span>
          <h1>把知识库整理成一套演示</h1>
          <p>当前项目还没有课件内容，可以使用已有资料与演示要求重新生成。</p>
          <el-button type="primary" size="large" :icon="MagicStick" :disabled="!canGenerate" @click="generatePpt">开始生成</el-button>
        </div>
      </main>

      <aside class="ai-sidebar">
        <div class="assistant-head">
          <span>✦</span>
          <div><b>AI 助手</b><small>对话修改课件 · 支持附图</small></div>
        </div>

        <div ref="chatThread" class="assistant-chat">
          <div
            v-for="message in chatMessages"
            :key="message.id"
            class="chat-message"
            :class="message.role"
          >
            <span>{{ message.role === 'assistant' ? 'Any2PPT' : '你' }}</span>
            <p>{{ message.text }}</p>
            <small v-if="message.imageName">📎 {{ message.imageName }}</small>
          </div>
          <div v-if="busy === 'chat'" class="chat-message assistant thinking">
            <span>Any2PPT</span>
            <p><i /><i /><i /></p>
          </div>
        </div>

        <div class="chat-composer">
          <div v-if="chatImage" class="chat-attachment">
            <img :src="chatImagePreview" alt="" />
            <span><b>{{ chatImage.name }}</b><small>{{ chatUploadProgress ? `上传 ${chatUploadProgress}%` : '将随消息发送' }}</small></span>
            <button type="button" aria-label="移除图片" :disabled="busy === 'chat'" @click="clearChatImage">×</button>
          </div>
          <textarea
            v-model="chatInput"
            :disabled="!selectedSlide || !!busy || markdownDirty || markdownSaving"
            maxlength="1000"
            placeholder="例如：精简当前页；或附图后输入“放到第 3 页右侧”…"
            @keydown.meta.enter.prevent="sendChat"
            @keydown.ctrl.enter.prevent="sendChat"
          />
          <div>
            <label class="chat-attach" title="添加图片">
              <input hidden type="file" accept=".png,.jpg,.jpeg,.webp" :disabled="!!busy" @change="pickChatImage" />
              <el-icon><Paperclip /></el-icon>
              <span>添加图片</span>
            </label>
            <small>⌘ Enter 发送</small>
            <button type="button" :disabled="(!chatInput.trim() && !chatImage) || !selectedSlide || !!busy || markdownDirty || markdownSaving" @click="sendChat">
              <el-icon><MagicStick /></el-icon>
            </button>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.editor-app{height:100vh;min-width:1040px;overflow:hidden;background:#f2f5f3;color:#18221e}.workbench-generation-lock{position:fixed;z-index:3000;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px;background:rgba(244,248,245,.97);text-align:center;backdrop-filter:blur(18px)}.lock-orbit{width:82px;height:82px;display:grid;place-items:center;margin-bottom:24px;border-radius:25px;background:#0eaa79;color:#fff;font-size:30px;box-shadow:0 18px 45px rgba(14,170,121,.25);animation:lockPulse 2s ease-in-out infinite}.workbench-generation-lock>span{color:#0b9168;font-size:10px;font-weight:800;letter-spacing:1.8px}.workbench-generation-lock h1{margin:12px 0 8px;font-family:"Songti SC",serif;font-size:38px}.workbench-generation-lock>p{margin:0;color:#748078}.lock-progress{width:min(520px,70vw);margin-top:30px;text-align:right}.lock-progress b{display:block;margin-bottom:8px;color:#0b9168}.lock-progress :deep(.el-progress-bar__inner){background:#0eaa79}.workbench-generation-lock>small{margin-top:20px;color:#8d9791}@keyframes lockPulse{50%{transform:scale(1.06)}}.editor-topbar{height:64px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:0 18px;border-bottom:1px solid #dde4df;background:rgba(255,255,255,.96)}.editor-brand,.editor-title,.editor-actions{display:flex;align-items:center}.editor-brand{gap:10px}.editor-brand>button{width:34px;height:34px;display:grid;place-items:center;border:0;border-radius:9px;background:#f1f5f2;color:#53615a;cursor:pointer}.mini-brand{width:31px;height:31px;display:flex;align-items:end;justify-content:center;gap:2px;padding:7px;border-radius:9px;background:#0eaa79}.mini-brand i{width:3px;border-radius:3px;background:#fff}.mini-brand i:nth-child(1){height:8px}.mini-brand i:nth-child(2){height:14px}.mini-brand i:nth-child(3){height:10px}.editor-brand div{display:grid}.editor-brand b{font-size:14px}.editor-brand small{color:#89928d;font-size:10px}.editor-title{gap:10px}.editor-title>b{font-size:14px}.editor-title>span{padding:4px 8px;border-radius:999px;background:#eff5f1;color:#78847d;font-size:10px}.editor-actions{justify-self:end;gap:8px}.editor-actions .el-select{width:112px}.editor-actions :deep(.el-button--primary){--el-button-bg-color:#0eaa79;--el-button-border-color:#0eaa79;--el-button-hover-bg-color:#087f5b;--el-button-hover-border-color:#087f5b}.editor-body{height:calc(100vh - 64px);display:grid;grid-template-columns:158px minmax(560px,1fr) 340px}.slides-sidebar{padding:16px 10px;border-right:1px solid #dce3de;background:#f7f9f7;overflow:auto}.add-slide{width:76px;height:28px;display:block;margin:0 auto 13px;border:0;border-radius:999px;background:#113f31;color:#fff;font-size:18px;cursor:not-allowed}.slide-thumb{width:100%;display:grid;grid-template-columns:18px 1fr;gap:5px;align-items:start;margin-bottom:9px;padding:4px;border:1px solid transparent;border-radius:9px;background:transparent;color:#7d8781;text-align:left;cursor:pointer}.slide-thumb>span,.slide-placeholder>span{padding-top:5px;font-size:10px}.slide-thumb>div{position:relative;aspect-ratio:16/9;display:flex;flex-direction:column;justify-content:center;overflow:hidden;padding:8px;border:1px solid #dfe5e1;border-radius:5px;background:#fff;box-shadow:0 2px 6px rgba(31,50,40,.04)}.slide-thumb i{position:absolute;right:7px;bottom:6px;width:20px;height:20px;border-radius:50%;opacity:.5}.slide-thumb b{position:relative;z-index:1;display:-webkit-box;overflow:hidden;font-family:"Songti SC",serif;font-size:9px;line-height:1.25;-webkit-line-clamp:2;-webkit-box-orient:vertical}.slide-thumb small{position:relative;z-index:1;margin-top:4px;overflow:hidden;color:inherit;font-size:6px;opacity:.6;text-overflow:ellipsis;white-space:nowrap}.slide-thumb:hover>div{border-color:#a9cfc0}.slide-thumb.active{color:#0b9168}.slide-thumb.active>div{border:2px solid #0eaa79;box-shadow:0 4px 14px rgba(14,170,121,.12)}.slide-placeholder{display:grid;grid-template-columns:18px 1fr;gap:5px;color:#9ca59f;font-size:10px}.slide-placeholder div{aspect-ratio:16/9;display:grid;place-items:center;border:1px dashed #cfd8d2;border-radius:5px}.editor-main{min-width:0;padding:18px clamp(18px,2.2vw,34px) 30px;overflow:auto;background:radial-gradient(circle at 50% 0,#fff 0,#f2f5f3 48%)}.workbench-alert{margin-bottom:12px}.canvas-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:0 auto 10px;max-width:980px}.canvas-heading>div{display:flex;align-items:center;gap:10px}.canvas-heading span{color:#89928d;font-size:10px;letter-spacing:1px}.canvas-heading b{font-family:"Songti SC",serif;font-size:17px}.current-images{max-width:980px;display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin:9px auto;color:#7a8498;font-size:11px}.deck-empty{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:40px}.deck-empty h1{margin:15px 0 8px;font-family:"Songti SC",serif;font-size:36px}.deck-empty p{max-width:500px;margin:0 0 24px;color:#7c8781;line-height:1.75}.deck-empty :deep(.el-button--primary){--el-button-bg-color:#0eaa79;--el-button-border-color:#0eaa79}.empty-orbit{width:130px;height:110px;display:grid;place-items:center;margin-bottom:20px;border-radius:40% 60% 55% 45%;background:radial-gradient(circle,#baf2dc,#e8f8f1 65%);box-shadow:0 20px 45px rgba(14,170,121,.16)}.empty-orbit span{display:grid;place-items:center;width:64px;height:54px;border-radius:14px;background:#0eaa79;color:#fff;font:700 20px ui-monospace,monospace}.ai-sidebar{display:flex;min-width:0;flex-direction:column;border-left:1px solid #dce3de;background:#f8faf9}.assistant-head{height:62px;flex:0 0 auto;display:flex;align-items:center;gap:10px;padding:0 19px;border-bottom:1px solid #e3e8e5;background:#fff}.assistant-head>span{color:#0eaa79;font-size:22px}.assistant-head div{display:grid}.assistant-head b{font-size:15px}.assistant-head small{margin-top:2px;color:#929a96;font-size:9px}.assistant-chat{flex:1;min-height:0;display:flex;flex-direction:column;gap:12px;padding:18px 14px;overflow:auto}.chat-message{max-width:90%;align-self:flex-start}.chat-message.user{align-self:flex-end}.chat-message>span{display:block;margin:0 5px 5px;color:#99a29d;font-size:9px}.chat-message.user>span{text-align:right}.chat-message p{margin:0;padding:11px 13px;border:1px solid #dfe7e2;border-radius:6px 15px 15px 15px;background:#fff;color:#35423b;font-size:11px;line-height:1.65;white-space:pre-wrap}.chat-message.user p{border-color:#0eaa79;border-radius:15px 6px 15px 15px;background:#0eaa79;color:#fff}.chat-message>small{display:block;margin:5px;color:#7d8982;font-size:9px}.chat-message.thinking p{display:flex;gap:4px;width:50px}.chat-message.thinking i{width:5px;height:5px;border-radius:50%;background:#0eaa79;animation:chatDot 1s infinite alternate}.chat-message.thinking i:nth-child(2){animation-delay:.2s}.chat-message.thinking i:nth-child(3){animation-delay:.4s}@keyframes chatDot{to{opacity:.25;transform:translateY(-2px)}}.chat-composer{flex:0 0 auto;margin:12px;padding:10px;border:1px solid #d9e3dd;border-radius:16px;background:#fff;box-shadow:0 12px 32px rgba(36,53,44,.08)}.chat-composer textarea{display:block;width:100%;height:86px;resize:none;border:0;outline:0;padding:3px;background:transparent;color:#25312b;font-size:11px;line-height:1.6}.chat-composer textarea::placeholder{color:#a1aaa5}.chat-composer>div:last-child{display:flex;align-items:center;gap:8px}.chat-composer>div:last-child>small{margin-left:auto;color:#a1a8a4;font-size:9px}.chat-composer>div:last-child>button{width:36px;height:36px;display:grid;place-items:center;border:0;border-radius:50%;background:#0eaa79;color:#fff;cursor:pointer}.chat-composer>div:last-child>button:disabled{background:#cbd5cf;cursor:not-allowed}.chat-attach{display:flex;align-items:center;gap:4px;color:#637169;font-size:10px;cursor:pointer}.chat-attachment{display:grid!important;grid-template-columns:42px minmax(0,1fr) 24px;gap:8px;align-items:center;margin-bottom:8px;padding:7px;border-radius:10px;background:#f1f7f4}.chat-attachment img{width:42px;height:34px;border-radius:6px;object-fit:cover}.chat-attachment span{display:grid;min-width:0}.chat-attachment b{overflow:hidden;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.chat-attachment small{color:#8c9690;font-size:8px}.chat-attachment button{border:0;background:transparent;color:#8c9690;cursor:pointer}@media(max-width:1260px){.editor-body{grid-template-columns:136px minmax(540px,1fr) 300px}.editor-actions .el-button span{display:none}.editor-actions .el-button{padding:8px 11px}.editor-title{display:none}}@media(max-height:760px){.chat-composer textarea{height:58px}}
</style>
