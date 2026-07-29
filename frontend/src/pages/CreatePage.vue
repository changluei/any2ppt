<script setup lang="ts">
/**
 * 创建首页：浏览/筛选主题，选中后展开生成向导。
 *
 * 用户填写独立标题与 PPT 要求，可多选知识库并可选上传资料；提交后建立
 * generationSession 并跳到锁定页，真正上传和创建任务由 GenerationPage 完成。
 */
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ArrowRight, Check, CloseBold, Document, MagicStick, UploadFilled } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import type { KnowledgeBase, ProjectInput, ThemeDescriptor } from '../types'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import ThemePreview from '../components/ThemePreview.vue'
import { beginGenerationSession } from '../services/generationSession'
import { useProjectStore } from '../stores/project'
import { validateSourceFile } from '../utils/files'
import { generationPath, workbenchPath } from '../utils/workbench'

type Category = '全部' | '简洁' | '科技' | '学术' | '创意' | '深色'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const themes = ref<ThemeDescriptor[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const category = ref<Category>('全部')
const builder = ref<HTMLElement>()
const editingId = ref('')
const prompt = ref('')
const selectedFiles = ref<File[]>([])
const generationStage = ref('')
const categories: Category[] = ['全部', '简洁', '科技', '学术', '创意', '深色']

const blankForm = (): ProjectInput => ({
  name: '',
  subject: '综合',
  grade: '通用',
  textbook_version: '',
  lesson_topic: '',
  lesson_count: 1,
  student_profile: '',
  teacher_requirements: '',
  theme_id: '',
  knowledge_base_ids: ['personal'],
})
const form = reactive<ProjectInput>(blankForm())

const selectedTheme = computed(() => themes.value.find((theme) => theme.id === form.theme_id))
const filteredThemes = computed(() => themes.value.filter((theme) => {
  if (category.value === '全部') return true
  const text = [theme.name, theme.description, theme.package, ...theme.keywords].join(' ').toLowerCase()
  const categoryTerms: Record<Exclude<Category, '全部'>, string[]> = {
    简洁: ['简洁', '极简', '通用', '清晰', '低饱和'],
    科技: ['科技', '数学', '逻辑', '图解', '结构', '代码', '工程'],
    学术: ['学术', '人文', '阅读', '正式', '历史', '论文', '研究'],
    创意: ['创意', '活泼', '互动', '探究', '高级', '图标', '路演'],
    深色: ['深色', '暗色', 'dark', '代码', '北欧'],
  }
  return categoryTerms[category.value].some((term) => text.includes(term))
}))

function sourceLabel(theme: ThemeDescriptor) {
  return ['default', 'seriph', 'apple-basic', 'bricks', 'shibainu'].includes(theme.id) ? '官方' : '社区'
}

async function load() {
  // 主题目录与知识库目录并行加载；编辑已有项目时再回填项目值。
  loading.value = true
  error.value = ''
  try {
    ;[themes.value, knowledgeBases.value] = await Promise.all([
      api.themes(),
      import('../api/knowledgeBases').then(({ knowledgeBasesApi }) => knowledgeBasesApi.list()),
    ])
    const projectId = String(route.query.edit || '')
    if (projectId) {
      const project = await api.project(projectId)
      editingId.value = project.id
      Object.assign(form, {
        name: project.name,
        subject: project.subject,
        grade: project.grade,
        textbook_version: project.textbook_version,
        lesson_topic: project.lesson_topic,
        lesson_count: project.lesson_count,
        student_profile: project.student_profile,
        teacher_requirements: project.teacher_requirements,
        theme_id: project.theme_id,
        knowledge_base_ids: [...project.knowledge_base_ids],
      })
      prompt.value = project.teacher_requirements || project.lesson_topic
      await nextTick()
      builder.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  } catch (requestError) {
    error.value = (requestError as Error).message
  } finally {
    loading.value = false
  }
}

async function chooseTheme(theme: ThemeDescriptor) {
  // 选择卡片只改变本地状态并展开向导，真正下载主题发生在创建项目时。
  form.theme_id = theme.id
  await nextTick()
  builder.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function addFiles(files?: FileList | File[]) {
  // 请求前先做体验性校验；后端仍会执行权威的格式和体积检查。
  if (!files || saving.value) return
  const incoming = Array.from(files)
  for (const file of incoming) {
    const validationError = validateSourceFile(file)
    if (validationError) {
      ElMessage.warning(`${file.name}：${validationError}`)
      continue
    }
    const duplicated = selectedFiles.value.some((item) => item.name === file.name && item.size === file.size)
    if (!duplicated) selectedFiles.value.push(file)
  }
  if (selectedFiles.value.length > 8) {
    selectedFiles.value = selectedFiles.value.slice(0, 8)
    ElMessage.warning('一次最多上传 8 份资料')
  }
}

function pickFiles(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles(input.files || undefined)
  input.value = ''
}

function removeFile(index: number) {
  selectedFiles.value.splice(index, 1)
}

function fillDemo() {
  prompt.value = '为小学三年级科学课制作一份“水的三态变化”课堂演示。控制在 12 页左右，用生活中的水蒸气、冰块和雨水作为例子，包含观察任务、变化过程对比和课堂小结，语言简洁、有互动感。'
}

async function saveAndGenerate() {
  // form.name 与 prompt 分开保存，避免把用户描述错误地用作演示标题。
  const description = prompt.value.trim()
  if (!form.theme_id) return ElMessage.warning('请先选择一个演示主题')
  if (form.name.trim().length < 2) return ElMessage.warning('请先填写 PPT 标题')
  if (description.length < 5) return ElMessage.warning('请描述你想生成什么样的 PPT')

  const title = form.name.trim()
  Object.assign(form, {
    name: title,
    subject: form.subject.trim() || '综合',
    grade: form.grade.trim() || '通用',
    lesson_topic: form.lesson_topic.trim() || title,
    teacher_requirements: description,
  })

  saving.value = true
  generationStage.value = editingId.value ? '正在保存演示信息' : '正在进入生成流程'
  try {
    if (editingId.value) {
      const project = await api.updateProject(editingId.value, form)
      projectStore.select(project.id)
      ElMessage.success('演示信息已更新')
      await router.push(workbenchPath(project.id))
      return
    }

    // File 留在内存，其余状态进入 sessionStorage，随后由生成锁定页接管。
    beginGenerationSession({
      mode: 'create',
      prompt: description,
      form: { ...form },
      files: selectedFiles.value,
      knowledgeBaseIds: form.knowledge_base_ids,
    })
    await router.push(generationPath)
  } catch (requestError) {
    ElMessage.error((requestError as Error).message)
  } finally {
    saving.value = false
    generationStage.value = ''
  }
}

onMounted(load)
</script>

<template>
  <section class="create-page">
    <div class="create-hero">
      <div class="hero-pill"><span>✦</span> AI + SLIDEV</div>
      <h1>先选一副好骨架，<em>再把想法变成演示。</em></h1>
      <p>浏览主题只读取预览；选择主题、补充可选资料并描述需求后，Any2PPT 会直接开始生成。</p>
    </div>

    <AppLoading v-if="loading" />
    <AppError v-else-if="error" :error="error" @retry="load" />
    <template v-else>
      <div class="catalog-head">
        <div>
          <span class="section-number">01 / THEMES</span>
          <h2>选择一个主题</h2>
          <p>来自 Slidev 官方与社区生态</p>
        </div>
        <span>当前展示 {{ filteredThemes.length }} 个精选预览</span>
      </div>

      <div class="category-tabs" role="tablist" aria-label="主题分类">
        <button
          v-for="item in categories"
          :key="item"
          type="button"
          :class="{ active: category === item }"
          @click="category = item"
        >
          {{ item }}
        </button>
      </div>

      <div v-if="filteredThemes.length" class="theme-gallery">
        <article
          v-for="theme in filteredThemes"
          :key="theme.id"
          class="gallery-card"
          :class="{ selected: form.theme_id === theme.id }"
        >
          <button type="button" class="gallery-preview" @click="chooseTheme(theme)">
            <ThemePreview :theme="theme" />
            <span class="preview-action">
              {{ form.theme_id === theme.id ? '已选择' : '选择这个主题' }}
              <el-icon><Check v-if="form.theme_id === theme.id" /><ArrowRight v-else /></el-icon>
            </span>
          </button>
          <div class="gallery-copy">
            <div>
              <h3>{{ theme.name }}</h3>
              <span>{{ sourceLabel(theme) }}</span>
            </div>
            <p>{{ theme.description }}</p>
            <div class="gallery-meta">
              <span><i :style="{ background: theme.palette.accent }" /> Slidev</span>
              <span>{{ theme.density === 'low' ? '舒展' : theme.density === 'high' ? '紧凑' : '均衡' }}</span>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="catalog-empty">这个分类暂时没有可用主题。</div>

      <section v-if="selectedTheme" ref="builder" class="create-builder">
        <div class="builder-preview">
          <span class="section-number">02 / CREATE</span>
          <div class="selected-theme-preview"><ThemePreview :theme="selectedTheme" /></div>
          <div class="builder-theme-copy">
            <span>已选主题 · {{ sourceLabel(selectedTheme) }}</span>
            <h2>{{ selectedTheme.name }}</h2>
            <p>{{ selectedTheme.design_guidance }}</p>
            <button type="button" @click="form.theme_id = ''">重新选择主题</button>
          </div>
        </div>

        <div class="builder-form">
          <div class="builder-title">
            <div>
              <span>{{ editingId ? 'EDIT PRESENTATION' : 'DESCRIBE & GENERATE' }}</span>
              <h2>{{ editingId ? '更新演示信息' : '描述你想要的 PPT' }}</h2>
            </div>
            <el-button v-if="!editingId" text @click="fillDemo">填入示例</el-button>
          </div>

          <div class="create-step-head description-head">
            <span>01</span>
            <div><b>PPT 标题</b><small>标题独立于生成要求，不会再从描述中自动截取</small></div>
          </div>
          <el-input
            v-model="form.name"
            size="large"
            maxlength="120"
            show-word-limit
            placeholder="例如：2026 年新能源汽车市场趋势"
          />

          <div class="create-step-head description-head">
            <span>02</span>
            <div><b>选择知识库</b><small>可多选；AI 会同时检索所选资料并标注引用依据</small></div>
          </div>
          <el-checkbox-group v-model="form.knowledge_base_ids" class="generation-kb-grid">
            <el-checkbox
              v-for="library in knowledgeBases"
              :key="library.id"
              :value="library.id"
              :disabled="library.status === 'importing' || library.status === 'failed'"
              border
            >
              <span class="generation-kb-copy">
                <b>{{ library.name }}</b>
                <small>
                  {{ library.status === 'importing' ? '正在导入' : library.status === 'failed' ? '暂不可用' : `${library.chunk_count.toLocaleString()} 个知识片段` }}
                </small>
              </span>
            </el-checkbox>
          </el-checkbox-group>

          <template v-if="!editingId">
            <div class="create-step-head">
              <span>03</span>
              <div><b>添加自己的资料</b><small>可选；上传后会自动沉淀到个人知识库</small></div>
            </div>
            <label
              class="prompt-upload"
              @dragover.prevent
              @drop.prevent="addFiles($event.dataTransfer?.files)"
            >
              <input hidden type="file" multiple accept=".pdf,.docx,.txt,.md" :disabled="saving" @change="pickFiles" />
              <el-icon><UploadFilled /></el-icon>
              <div><b>点击或拖放资料到这里</b><span>PDF / DOCX / TXT / Markdown，单文件不超过 20MB</span></div>
            </label>
            <div v-if="selectedFiles.length" class="selected-source-list">
              <div v-for="(file, index) in selectedFiles" :key="`${file.name}-${file.size}`">
                <el-icon><Document /></el-icon>
                <span><b>{{ file.name }}</b><small>{{ (file.size / 1024).toFixed(1) }} KB</small></span>
                <button type="button" aria-label="移除资料" :disabled="saving" @click="removeFile(index)"><el-icon><CloseBold /></el-icon></button>
              </div>
            </div>
          </template>

          <div class="create-step-head description-head">
            <span>{{ editingId ? '03' : '04' }}</span>
            <div><b>描述演示需求</b><small>主题、受众、页数、重点和表达方式都可以写在这里</small></div>
          </div>
          <el-input
            v-model="prompt"
            class="generation-prompt"
            type="textarea"
            :rows="7"
            maxlength="3000"
            show-word-limit
            placeholder="例如：为新员工制作一份 12 页左右的产品培训 PPT，先讲用户痛点，再介绍三个核心功能，加入一页竞品对比和一页实施计划，语言简洁、数据感强……"
          />

          <details class="advanced-settings">
            <summary>高级信息（可选）</summary>
            <div class="form-row">
              <el-form-item label="核心主题">
                <el-input v-model="form.lesson_topic" maxlength="160" placeholder="留空将使用 PPT 标题" />
              </el-form-item>
            </div>
            <div class="form-row three">
              <el-form-item label="领域 / 学科"><el-input v-model="form.subject" maxlength="40" /></el-form-item>
              <el-form-item label="受众"><el-input v-model="form.grade" maxlength="40" /></el-form-item>
              <el-form-item label="课时"><el-input-number v-model="form.lesson_count" :min="1" :max="8" /></el-form-item>
            </div>
          </details>

          <div class="builder-submit">
            <p><i /> {{ generationStage || (selectedFiles.length ? `会先读取 ${selectedFiles.length} 份资料，再按 ${selectedTheme.name} 生成` : `本次不使用资料，按 ${selectedTheme.name} 生成`) }}</p>
            <el-button type="primary" size="large" :loading="saving" :disabled="saving || form.name.trim().length < 2 || prompt.trim().length < 5" @click="saveAndGenerate">
              <el-icon><MagicStick /></el-icon>
              {{ saving ? generationStage || '正在处理…' : editingId ? '保存并进入编辑器' : '直接生成 PPT' }}
            </el-button>
          </div>
        </div>
      </section>
    </template>
  </section>
</template>
