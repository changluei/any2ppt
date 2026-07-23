<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Delete, EditPen, MoreFilled, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import type { Project, ProjectInput, ThemeDescriptor } from '../types'
import AppEmpty from '../components/AppEmpty.vue'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import { useProjectStore } from '../stores/project'
import { validateProject, workbenchPath } from '../utils/workbench'

const router = useRouter()
const projectStore = useProjectStore()
const projects = ref<Project[]>([])
const themes = ref<ThemeDescriptor[]>([])
const loading = ref(true)
const error = ref('')
const dialog = ref(false)
const saving = ref(false)
const step = ref(0)
const query = ref('')
const editingId = ref('')
const recommendedThemeId = ref('')
const recommendationReason = ref('')
const previewTheme = ref<ThemeDescriptor>()
const previewVisible = ref(false)

const blankForm = (): ProjectInput => ({
  name: '',
  subject: '语文',
  grade: '小学三年级',
  textbook_version: '',
  lesson_topic: '',
  lesson_count: 1,
  student_profile: '',
  teacher_requirements: '',
  theme_id: '',
})
const form = reactive<ProjectInput>(blankForm())

const filteredProjects = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return projects.value
  return projects.value.filter(project =>
    [project.name, project.lesson_topic, project.subject, project.grade]
      .some(value => value.toLowerCase().includes(keyword)),
  )
})
const selectedTheme = computed(() => themes.value.find(theme => theme.id === form.theme_id))

function themeOf(project: Project) {
  return themes.value.find(theme => theme.id === project.theme_id)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [projectRows, themeRows] = await Promise.all([api.projects(), api.themes()])
    projects.value = projectRows
    themes.value = themeRows
  } catch (requestError) {
    error.value = (requestError as Error).message
  } finally {
    loading.value = false
  }
}

function openProject(project: Project) {
  projectStore.select(project.id)
  router.push(workbenchPath(project.id))
}

function resetDialog() {
  Object.assign(form, blankForm())
  editingId.value = ''
  recommendedThemeId.value = ''
  recommendationReason.value = ''
  step.value = 0
}

function startCreate() {
  resetDialog()
  dialog.value = true
}

function editProject(project: Project) {
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
  })
  editingId.value = project.id
  recommendedThemeId.value = ''
  recommendationReason.value = ''
  step.value = 0
  dialog.value = true
}

function fillDemo() {
  resetDialog()
  Object.assign(form, {
    name: '水的三态变化演示课',
    subject: '科学',
    grade: '小学三年级',
    textbook_version: '自编公开样例',
    lesson_topic: '水的三态变化',
    lesson_count: 1,
    student_profile: '学生能描述常见生活现象，喜欢动手观察。',
    teacher_requirements: '单课时40分钟，突出观察、描述和安全提示。',
  })
  dialog.value = true
}

async function recommendTheme() {
  try {
    const theme = await api.recommendTheme(form)
    recommendedThemeId.value = theme.id
    recommendationReason.value = theme.match_reason
    if (!form.theme_id) form.theme_id = theme.id
  } catch {
    if (!form.theme_id) form.theme_id = themes.value[0]?.id || 'default'
  }
}

async function next() {
  if (step.value === 0) {
    const message = validateProject({ ...form, theme_id: form.theme_id || 'default' })
    if (message) return ElMessage.warning(message)
    await recommendTheme()
  }
  if (step.value === 1 && !form.theme_id) return ElMessage.warning('请选择一个课件模板')
  step.value++
}

function showPreview(theme: ThemeDescriptor) {
  previewTheme.value = theme
  previewVisible.value = true
}

async function saveProject() {
  const message = validateProject(form)
  if (message) return ElMessage.warning(message)
  saving.value = true
  try {
    const project = editingId.value
      ? await api.updateProject(editingId.value, form)
      : await api.createProject(form)
    projectStore.select(project.id)
    dialog.value = false
    if (project.theme_status === 'failed') {
      ElMessage.warning('项目已保存，但模板下载失败，可在项目卡片中重试')
    } else {
      ElMessage.success(editingId.value ? '项目已更新' : '模板已准备，项目创建成功')
    }
    await router.push(workbenchPath(project.id))
  } catch (requestError) {
    ElMessage.error((requestError as Error).message)
  } finally {
    saving.value = false
  }
}

async function deleteProject(project: Project) {
  try {
    await ElMessageBox.confirm(
      `将永久删除“${project.name}”及其中的资料、图片、课件和导出文件。`,
      '删除项目',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await api.deleteProject(project.id)
    projects.value = projects.value.filter(item => item.id !== project.id)
    if (projectStore.currentProjectId === project.id) projectStore.select('')
    ElMessage.success('项目已删除')
  } catch (requestError) {
    if (requestError !== 'cancel' && requestError !== 'close') {
      ElMessage.error((requestError as Error).message)
    }
  }
}

async function retryTheme(project: Project) {
  try {
    const updated = await api.prepareProjectTheme(project.id)
    const index = projects.value.findIndex(item => item.id === project.id)
    if (index >= 0) projects.value[index] = updated
    ElMessage.success('模板已重新下载')
  } catch (requestError) {
    ElMessage.error((requestError as Error).message)
  }
}

function handleCommand(command: string, project: Project) {
  if (command === 'edit') editProject(project)
  if (command === 'delete') deleteProject(project)
  if (command === 'retry') retryTheme(project)
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head project-page-head">
      <div>
        <div class="head-kicker">{{ projects.length }} 个项目</div>
        <h2>备课项目</h2>
        <p>先确定课件风格，再准备资料和生成 PPT。</p>
      </div>
      <div class="project-tools">
        <el-input v-model="query" clearable placeholder="搜索项目或课题" class="project-search">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button @click="fillDemo">填入演示课题</el-button>
        <el-button type="primary" size="large" @click="startCreate">＋ 选择模板并开始</el-button>
      </div>
    </div>

    <AppLoading v-if="loading" />
    <AppError v-else-if="error" :error="error" @retry="load" />
    <AppEmpty v-else-if="!projects.length" text="还没有备课项目，先选择一个模板开始吧" />
    <AppEmpty v-else-if="!filteredProjects.length" text="没有找到匹配的项目" />
    <div v-else class="project-grid">
      <article
        v-for="project in filteredProjects"
        :key="project.id"
        class="panel project-card"
        tabindex="0"
        @click="openProject(project)"
        @keyup.enter="openProject(project)"
      >
        <img
          v-if="themeOf(project)"
          class="project-theme-thumb"
          :src="themeOf(project)?.preview_url"
          :alt="`${themeOf(project)?.name}模板预览`"
        />
        <div class="project-card-body">
          <div class="card-head">
            <el-tag effect="plain">{{ project.grade }} · {{ project.subject }}</el-tag>
            <el-dropdown trigger="click" @command="handleCommand($event, project)">
              <el-button text circle aria-label="项目操作" @click.stop>
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit"><el-icon><EditPen /></el-icon>编辑项目</el-dropdown-item>
                  <el-dropdown-item v-if="project.theme_status === 'failed'" command="retry">
                    <el-icon><Refresh /></el-icon>重新下载模板
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided class="danger-item">
                    <el-icon><Delete /></el-icon>删除项目
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <h3>{{ project.name }}</h3>
          <p>{{ project.lesson_topic }}</p>
          <div class="theme-line">
            <span class="theme-dot" :style="{ background: themeOf(project)?.palette.accent }" />
            {{ themeOf(project)?.name || '清晰通用' }}
            <el-tag v-if="project.theme_status === 'failed'" size="small" type="danger">下载失败</el-tag>
          </div>
          <div class="meta">{{ project.textbook_version || '未指定教材版本' }} · {{ project.lesson_count }} 课时</div>
          <div class="meta">更新于 {{ new Date(project.updated_at).toLocaleString() }}</div>
        </div>
      </article>
    </div>

    <el-dialog
      v-model="dialog"
      :title="editingId ? '编辑备课项目' : '创建备课项目'"
      width="min(1040px, 94vw)"
      destroy-on-close
      @closed="resetDialog"
    >
      <el-steps :active="step" finish-status="success" class="steps">
        <el-step title="课程信息" />
        <el-step title="选择模板" />
        <el-step title="学情与要求" />
        <el-step title="确认" />
      </el-steps>
      <el-form label-position="top">
        <template v-if="step === 0">
          <div class="row">
            <el-form-item class="grow" label="项目名称" required><el-input v-model="form.name" maxlength="120" /></el-form-item>
            <el-form-item class="grow" label="课题" required><el-input v-model="form.lesson_topic" maxlength="160" /></el-form-item>
          </div>
          <div class="row">
            <el-form-item class="grow" label="学科" required>
              <el-select v-model="form.subject" style="width:100%">
                <el-option v-for="item in ['语文','数学','英语','科学','道德与法治']" :key="item" :value="item" />
              </el-select>
            </el-form-item>
            <el-form-item class="grow" label="年级" required><el-input v-model="form.grade" maxlength="40" /></el-form-item>
            <el-form-item label="课时"><el-input-number v-model="form.lesson_count" :min="1" :max="8" /></el-form-item>
          </div>
          <el-form-item label="教材版本"><el-input v-model="form.textbook_version" maxlength="80" /></el-form-item>
        </template>

        <template v-else-if="step === 1">
          <div class="theme-step-head">
            <div>
              <h3>选择课件模板</h3>
              <p>这里加载的是预览图和模板说明，不会下载主题源码。</p>
            </div>
            <el-tag v-if="recommendedThemeId" type="success" effect="light">已给出智能推荐</el-tag>
          </div>
          <div class="theme-grid">
            <article
              v-for="theme in themes"
              :key="theme.id"
              class="theme-card"
              :class="{ selected: form.theme_id === theme.id }"
              @click="form.theme_id = theme.id"
            >
              <div class="theme-preview-wrap">
                <img :src="theme.preview_url" :alt="`${theme.name}模板预览`" />
                <button type="button" class="preview-button" @click.stop="showPreview(theme)">查看大图</button>
                <span v-if="recommendedThemeId === theme.id" class="recommend-badge">推荐</span>
              </div>
              <div class="theme-card-copy">
                <div><b>{{ theme.name }}</b><span>{{ theme.density === 'low' ? '低密度' : '中密度' }}</span></div>
                <p>{{ theme.description }}</p>
                <div class="theme-keywords"><span v-for="word in theme.keywords.slice(0, 4)" :key="word">{{ word }}</span></div>
              </div>
            </article>
          </div>
          <el-alert
            v-if="recommendedThemeId"
            :title="`推荐理由：${recommendationReason}`"
            type="success"
            :closable="false"
            show-icon
          />
        </template>

        <template v-else-if="step === 2">
          <el-form-item label="班级特点 / 薄弱点（可选）">
            <el-input v-model="form.student_profile" type="textarea" :rows="4" maxlength="2000" show-word-limit />
          </el-form-item>
          <el-form-item label="教师补充要求（可选）">
            <el-input v-model="form.teacher_requirements" type="textarea" :rows="4" maxlength="3000" show-word-limit />
          </el-form-item>
          <el-alert
            title="生成时，AI 会读取所选模板支持的版式、信息密度和图片策略，安排封面、章节、步骤、比较等页面。"
            type="info"
            :closable="false"
          />
        </template>

        <div v-else class="confirm-grid">
          <div v-if="selectedTheme" class="confirm-theme">
            <img :src="selectedTheme.preview_url" :alt="`${selectedTheme.name}模板预览`" />
            <div><span>已选模板</span><b>{{ selectedTheme.name }}</b><p>{{ selectedTheme.description }}</p></div>
          </div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="项目">{{ form.name }}</el-descriptions-item>
            <el-descriptions-item label="课题">{{ form.lesson_topic }}</el-descriptions-item>
            <el-descriptions-item label="课程">{{ form.grade }} · {{ form.subject }}</el-descriptions-item>
            <el-descriptions-item label="教材">{{ form.textbook_version || '未指定' }}</el-descriptions-item>
            <el-descriptions-item label="学情" :span="2">{{ form.student_profile || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="补充要求" :span="2">{{ form.teacher_requirements || '未填写' }}</el-descriptions-item>
          </el-descriptions>
          <p class="download-note">确认后才会从 npm 下载这个模板；其他模板仍只保留描述和预览图。</p>
        </div>
      </el-form>
      <template #footer>
        <el-button v-if="step" @click="step--">上一步</el-button>
        <el-button v-if="step < 3" type="primary" @click="next">下一步</el-button>
        <el-button v-else type="primary" :loading="saving" :disabled="saving" @click="saveProject">
          {{ saving ? '正在准备模板…' : editingId ? '保存项目' : '确认并创建项目' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" :title="previewTheme?.name" width="min(920px, 92vw)" append-to-body>
      <img v-if="previewTheme" class="large-theme-preview" :src="previewTheme.preview_url" :alt="`${previewTheme.name}完整预览`" />
      <div v-if="previewTheme" class="preview-detail">
        <p>{{ previewTheme.design_guidance }}</p>
        <a :href="previewTheme.source_url" target="_blank" rel="noreferrer">查看 npm 模板来源</a>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
        <el-button type="primary" @click="form.theme_id = previewTheme?.id || form.theme_id; previewVisible = false">选择这个模板</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.project-page-head{align-items:center}.head-kicker{margin-bottom:5px;color:#8a93a6;font-size:12px}.project-tools{display:flex;align-items:center;gap:10px}.project-search{width:220px}.project-card{padding:0}.project-theme-thumb{display:block;width:100%;aspect-ratio:16/5.4;object-fit:cover;border-bottom:1px solid #eceef4}.project-card-body{padding:17px 20px 20px}.card-head{display:flex;align-items:center;justify-content:space-between}.project-card h3{margin:12px 0 7px}.project-card p{margin:0 0 10px}.project-card .meta{margin-top:7px}.theme-line{display:flex;align-items:center;gap:7px;margin:10px 0;color:#647087;font-size:13px}.theme-dot{width:8px;height:8px;border-radius:50%}.danger-item{color:#d84d4d}.steps{margin-bottom:26px}.theme-step-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.theme-step-head h3{margin:0 0 4px}.theme-step-head p{margin:0;color:#818a9c}.theme-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;max-height:500px;padding:2px 5px 14px 2px;overflow:auto}.theme-card{overflow:hidden;border:2px solid #e8eaf0;border-radius:14px;background:#fff;cursor:pointer;transition:.18s}.theme-card:hover{border-color:#bdc4ed;transform:translateY(-1px)}.theme-card.selected{border-color:#5c6bd8;box-shadow:0 0 0 3px rgba(92,107,216,.1)}.theme-preview-wrap{position:relative;background:#e8eaf0}.theme-preview-wrap img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover}.preview-button{position:absolute;right:9px;bottom:9px;padding:6px 9px;border:0;border-radius:7px;background:rgba(23,30,48,.76);color:white;cursor:pointer}.recommend-badge{position:absolute;left:9px;top:9px;padding:5px 9px;border-radius:20px;background:#47a36b;color:#fff;font-size:11px;font-weight:700}.theme-card-copy{padding:13px 14px}.theme-card-copy>div:first-child{display:flex;align-items:center;justify-content:space-between}.theme-card-copy b{font-size:15px}.theme-card-copy>div:first-child span{color:#9299a9;font-size:11px}.theme-card-copy p{min-height:38px;margin:7px 0;color:#6f798d;font-size:12px;line-height:1.55}.theme-keywords{display:flex;gap:5px;flex-wrap:wrap}.theme-keywords span{padding:3px 7px;border-radius:12px;background:#f1f2f7;color:#7b8497;font-size:10px}.confirm-grid{display:grid;gap:16px}.confirm-theme{display:grid;grid-template-columns:260px 1fr;gap:18px;align-items:center;padding:12px;border:1px solid #e5e7ee;border-radius:13px;background:#fafbfe}.confirm-theme img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px}.confirm-theme span,.confirm-theme b{display:block}.confirm-theme span{color:#8992a5;font-size:12px}.confirm-theme b{margin-top:4px;font-size:20px}.confirm-theme p{margin:7px 0 0;color:#727d91}.download-note{margin:0;color:#667085;font-size:13px}.large-theme-preview{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;border-radius:10px;background:#edf0f5}.preview-detail{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-top:14px}.preview-detail p{margin:0;color:#667085;line-height:1.6}.preview-detail a{flex:none;color:#5061cf}@media(max-width:1100px){.project-tools{flex-wrap:wrap}.theme-grid{grid-template-columns:1fr}}@media(max-width:820px){.project-search{width:100%}.confirm-theme{grid-template-columns:1fr}}
</style>
