<script setup lang="ts">
/**
 * 知识库管理页：查看三科官方库统计，并持续维护个人知识库。
 * 官方库只读；个人资料支持上传、状态轮询、失败重试和删除。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Collection, Delete, Document, RefreshRight, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { knowledgeBasesApi } from '../api/knowledgeBases'
import type { KnowledgeBase, Source } from '../types'
import AppEmpty from '../components/AppEmpty.vue'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import StatusTag from '../components/StatusTag.vue'
import { validateSourceFile } from '../utils/files'

const libraries = ref<KnowledgeBase[]>([])
const activeId = ref('personal')
const sources = ref<Source[]>([])
const loading = ref(true)
const error = ref('')
const uploading = ref(false)
const progress = ref(0)
const busyId = ref('')
let timer: number | undefined

const activeLibrary = computed(() => libraries.value.find((item) => item.id === activeId.value))

function formatCount(value: number) {
  return value >= 10000 ? `${(value / 10000).toFixed(value >= 100000 ? 0 : 1)} 万` : value.toLocaleString()
}

function libraryMark(library: KnowledgeBase) {
  return library.kind === 'personal' ? 'PERSONAL' : library.subject.toUpperCase()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    libraries.value = await knowledgeBasesApi.list()
    await loadSources()
  } catch (requestError) {
    error.value = (requestError as Error).message
  } finally {
    loading.value = false
  }
}

async function loadSources() {
  clearTimeout(timer)
  if (activeId.value !== 'personal') {
    sources.value = []
    return
  }
  try {
    sources.value = await knowledgeBasesApi.sources('personal')
    if (sources.value.some(({ status }) => ['uploaded', 'parsing', 'indexing'].includes(status))) {
      timer = window.setTimeout(async () => {
        await loadSources()
        libraries.value = await knowledgeBasesApi.list()
      }, 1800)
    }
  } catch (requestError) {
    error.value = (requestError as Error).message
  }
}

async function chooseLibrary(library: KnowledgeBase) {
  activeId.value = library.id
  await loadSources()
}

async function upload(file?: File) {
  if (!file || uploading.value) return
  const validationError = validateSourceFile(file)
  if (validationError) return ElMessage.warning(validationError)
  uploading.value = true
  progress.value = 0
  try {
    const source = await knowledgeBasesApi.upload(file, (value) => (progress.value = value))
    if (source.status === 'ready') ElMessage.success('这份资料已经在个人知识库中，可直接复用')
    else ElMessage.success('已归档到个人知识库，正在建立索引')
    activeId.value = 'personal'
    await loadSources()
  } catch (requestError) {
    ElMessage.error((requestError as Error).message)
  } finally {
    uploading.value = false
  }
}

function pick(event: Event) {
  const input = event.target as HTMLInputElement
  upload(input.files?.[0])
  input.value = ''
}

async function changeSource(source: Source, action: 'retry' | 'remove') {
  if (action === 'remove') {
    try {
      await ElMessageBox.confirm(`确定从个人知识库删除“${source.original_name}”吗？`, '删除资料')
    } catch {
      return
    }
  }
  busyId.value = source.id
  try {
    if (action === 'retry') await knowledgeBasesApi.retry(source.id)
    else await knowledgeBasesApi.remove(source.id)
    ElMessage.success(action === 'retry' ? '已重新开始索引' : '资料及索引已删除')
    await load()
  } catch (requestError) {
    ElMessage.error((requestError as Error).message)
  } finally {
    busyId.value = ''
  }
}

onMounted(load)
onUnmounted(() => clearTimeout(timer))
</script>

<template>
  <section class="knowledge-page">
    <header class="knowledge-head">
      <div>
        <span class="section-number">KNOWLEDGE SYSTEM</span>
        <h1>四个知识库，一次组合使用。</h1>
        <p>语文、数学、英语由系统维护；你上传的每份资料会持续沉淀到个人知识库，不再随演示项目重复创建。</p>
      </div>
      <div class="knowledge-total">
        <b>{{ formatCount(libraries.reduce((sum, item) => sum + item.chunk_count, 0)) }}</b>
        <span>可检索知识片段</span>
      </div>
    </header>

    <AppLoading v-if="loading" />
    <AppError v-else-if="error && !libraries.length" :error="error" @retry="load" />
    <template v-else>
      <div class="library-cards">
        <button
          v-for="library in libraries"
          :key="library.id"
          type="button"
          :class="['library-card', library.kind, { active: activeId === library.id }]"
          @click="chooseLibrary(library)"
        >
          <span class="library-card-mark">{{ libraryMark(library) }}</span>
          <span class="library-icon"><el-icon><Collection /></el-icon></span>
          <b>{{ library.name }}</b>
          <small>{{ library.description }}</small>
          <span class="library-stats">
            <i :class="library.status" />
            {{ library.status === 'importing' ? '正在导入' : library.status === 'failed' ? '导入失败' : `${formatCount(library.chunk_count)} 个片段` }}
          </span>
        </button>
      </div>

      <div class="knowledge-workspace">
        <section class="knowledge-panel library-detail">
          <div class="panel-heading">
            <div>
              <span>{{ activeLibrary?.kind === 'personal' ? '持续积累' : '系统维护 · 只读' }}</span>
              <h2>{{ activeLibrary?.name }}</h2>
            </div>
            <el-tag v-if="activeLibrary" effect="plain">{{ activeLibrary.document_count.toLocaleString() }} 份来源</el-tag>
          </div>

          <template v-if="activeId === 'personal'">
            <label
              :class="['personal-upload', { disabled: uploading }]"
              @dragover.prevent
              @drop.prevent="upload($event.dataTransfer?.files[0])"
            >
              <input hidden type="file" accept=".pdf,.docx,.txt,.md" :disabled="uploading" @change="pick" />
              <span><el-icon><UploadFilled /></el-icon></span>
              <div><b>添加到个人知识库</b><small>PDF / DOCX / TXT / Markdown，上传后自动去重并建立索引</small></div>
              <el-progress v-if="uploading" :percentage="progress" :show-text="false" />
            </label>

            <div class="source-list">
              <AppEmpty v-if="!sources.length" text="个人知识库还没有资料" />
              <article v-for="source in sources" v-else :key="source.id">
                <span class="source-icon"><el-icon><Document /></el-icon></span>
                <div>
                  <b>{{ source.original_name }}</b>
                  <small>{{ (source.size / 1024 / 1024).toFixed(2) }} MB · {{ new Date(source.created_at).toLocaleDateString() }}</small>
                  <em v-if="source.error_message">{{ source.error_message }}</em>
                </div>
                <StatusTag :status="source.status" />
                <el-button v-if="source.status === 'failed'" link :icon="RefreshRight" :loading="busyId === source.id" @click="changeSource(source, 'retry')" />
                <el-button link type="danger" :icon="Delete" :loading="busyId === source.id" @click="changeSource(source, 'remove')" />
              </article>
            </div>
          </template>

          <div v-else class="official-detail">
            <span class="official-watermark">{{ activeLibrary?.subject }}</span>
            <p>这套资料由 Any2PPT 统一构建与维护，生成时可与其他知识库一起勾选。官方库只读，避免个人上传内容影响基础学科资料。</p>
            <dl>
              <div><dt>知识片段</dt><dd>{{ activeLibrary?.chunk_count.toLocaleString() }}</dd></div>
              <div><dt>资料来源</dt><dd>{{ activeLibrary?.document_count.toLocaleString() }}</dd></div>
              <div><dt>当前状态</dt><dd>{{ activeLibrary?.status === 'ready' ? '可用' : activeLibrary?.status }}</dd></div>
            </dl>
          </div>
        </section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.knowledge-page{width:min(1420px,calc(100% - 72px));margin:0 auto;padding:72px 0 100px}.knowledge-head{display:flex;align-items:end;justify-content:space-between;gap:50px;margin-bottom:42px}.knowledge-head h1{margin:10px 0 12px;font-family:var(--display);font-size:46px;font-weight:550;letter-spacing:-2px}.knowledge-head p{max-width:760px;margin:0;color:#77817b;line-height:1.8}.knowledge-total{min-width:155px;display:grid;gap:2px;padding-left:24px;border-left:1px solid #dce4df}.knowledge-total b{font-family:var(--display);font-size:34px;color:var(--green-dark)}.knowledge-total span{color:#929b96;font-size:11px}.library-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:22px}.library-card{position:relative;min-height:184px;display:flex;flex-direction:column;align-items:flex-start;padding:23px;border:1px solid #dde5e0;border-radius:16px;background:#fff;color:var(--ink);text-align:left;cursor:pointer;transition:.2s}.library-card:hover,.library-card.active{transform:translateY(-3px);border-color:#8acdb2;box-shadow:0 18px 44px rgba(32,72,52,.09)}.library-card.active{background:#f4fbf7}.library-card-mark{position:absolute;right:17px;top:17px;color:#a0aaa4;font-size:9px;font-weight:800;letter-spacing:1px}.library-icon{width:38px;height:38px;display:grid;place-items:center;margin-bottom:19px;border-radius:11px;background:#eaf8f2;color:var(--green-dark);font-size:18px}.library-card.personal .library-icon{background:#172a22;color:white}.library-card>b{font-size:16px}.library-card>small{min-height:38px;margin-top:7px;color:#849089;font-size:11px;line-height:1.65}.library-stats{display:flex;align-items:center;gap:7px;margin-top:auto;color:#67736c;font-size:10px}.library-stats i{width:7px;height:7px;border-radius:50%;background:#aeb6b1}.library-stats i.ready{background:#10aa79}.library-stats i.importing{background:#e3a43c;animation:pulse 1.2s infinite}.library-stats i.failed{background:#d65757}.knowledge-workspace{display:block}.knowledge-panel{padding:28px;border:1px solid #dfe6e2;border-radius:18px;background:#fff}.panel-heading{display:flex;align-items:start;justify-content:space-between;margin-bottom:22px}.panel-heading span{color:#8e9892;font-size:9px;font-weight:750;letter-spacing:1.2px}.panel-heading h2{margin:6px 0 0;font-family:var(--display);font-size:26px}.personal-upload{position:relative;min-height:100px;display:flex;align-items:center;gap:15px;padding:19px;border:1px dashed #add2c1;border-radius:13px;background:#f5fbf8;cursor:pointer}.personal-upload.disabled{pointer-events:none;opacity:.6}.personal-upload>span{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;background:#dcf5e9;color:var(--green-dark);font-size:20px}.personal-upload>div{display:grid;gap:4px}.personal-upload b{font-size:12px}.personal-upload small{color:#88938d;font-size:9px}.personal-upload .el-progress{position:absolute;left:19px;right:19px;bottom:8px}.source-list{max-height:480px;overflow:auto;margin-top:18px}.source-list article{display:grid;grid-template-columns:36px minmax(0,1fr) auto 30px 30px;align-items:center;gap:10px;padding:12px 3px;border-bottom:1px solid #edf0ee}.source-icon{width:34px;height:34px;display:grid;place-items:center;border-radius:9px;background:#f0f4f1;color:#718078}.source-list article>div{min-width:0;display:grid;gap:3px}.source-list b{overflow:hidden;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.source-list small{color:#99a09c;font-size:9px}.source-list em{color:#cf5555;font-size:9px;font-style:normal}.official-detail{position:relative;min-height:320px;overflow:hidden;padding:36px;border-radius:14px;background:linear-gradient(135deg,#f3faf6,#edf5f1)}.official-watermark{position:absolute;right:-10px;bottom:-45px;color:rgba(14,145,104,.07);font-family:var(--display);font-size:190px}.official-detail p{position:relative;max-width:760px;margin:0;color:#617068;font-size:13px;line-height:2}.official-detail dl{position:relative;display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin-top:52px;border:1px solid #dce9e2;border-radius:12px;background:#dce9e2;overflow:hidden}.official-detail dl div{display:grid;gap:5px;padding:18px;background:rgba(255,255,255,.76)}.official-detail dt{color:#87918b;font-size:9px}.official-detail dd{margin:0;font-family:var(--display);font-size:21px}@keyframes pulse{50%{opacity:.35}}@media(max-width:1100px){.library-cards{grid-template-columns:repeat(2,1fr)}.knowledge-head h1{font-size:38px}}@media(max-width:700px){.knowledge-page{width:calc(100% - 28px)}.knowledge-head{align-items:start;flex-direction:column}.library-cards{grid-template-columns:1fr}}
</style>
