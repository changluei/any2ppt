<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import type { SlideImagePlacement, ThemeDescriptor } from '../types'

const props = withDefaults(defineProps<{
  markdown: string
  title?: string
  syncing?: boolean
  images?: SlideImagePlacement[]
  imageBaseUrl?: string
  themePalette?: ThemeDescriptor['palette']
  renderedPreviewUrl?: string
}>(), {
  title: '',
  syncing: false,
  images: () => [],
  imageBaseUrl: '',
  renderedPreviewUrl: '',
  themePalette: () => ({
    background: '#142b4d',
    surface: '#0b1930',
    text: '#f8fbff',
    accent: '#6be5c3',
  }),
})
const emit = defineEmits<{
  change: [markdown: string]
}>()

const draft = ref(props.markdown)
const displayedPreviewUrl = ref('')
const renderedLoaded = ref(false)
const renderedFailed = ref(false)
const previewLoading = ref(false)
let previewRequest = 0
const parser = new MarkdownIt({ html: false, linkify: true, breaks: true })
const dirty = computed(() => draft.value !== props.markdown)
function placementHtml(placement: SlideImagePlacement) {
  const url = `${props.imageBaseUrl}/${encodeURIComponent(placement.image_id)}/content`
  const background = placement.position === 'background'
  const image = `<img src="${url}" alt="" style="position:absolute;left:${placement.x}%;top:${placement.y}%;width:${placement.width}%;height:${placement.height}%;object-fit:cover;opacity:${placement.opacity};z-index:${background ? 0 : 3};border-radius:${background ? 0 : 14}px" />`
  if (!placement.caption || background) return image
  const caption = DOMPurify.sanitize(placement.caption)
  return image + `<div style="position:absolute;left:${placement.x}%;top:${Math.min(94, placement.y + placement.height + 1)}%;width:${placement.width}%;text-align:center;font-size:12px;opacity:.75;z-index:4">${caption}</div>`
}
const srcdoc = computed(() => {
  const rendered = DOMPurify.sanitize(parser.render(draft.value || ''))
  const title = DOMPurify.sanitize(props.title || '课件预览')
  const backgrounds = props.images.filter((item) => item.position === 'background').map(placementHtml).join('')
  const foregrounds = props.images.filter((item) => item.position !== 'background').map(placementHtml).join('')
  const palette = props.themePalette
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${title}</title><style>
  *{box-sizing:border-box}body{position:relative;overflow:hidden;margin:0;min-height:100vh;padding:8% 9%;font-family:Inter,"PingFang SC",sans-serif;
  color:${palette.text};background:radial-gradient(circle at 80% 10%,${palette.surface},${palette.background} 65%)}
  body>*:not(img){position:relative;z-index:2}
  h1{font-size:clamp(32px,5vw,64px);line-height:1.15;margin:0 0 5%}h2{font-size:clamp(24px,3vw,42px)}
  p,li{font-size:clamp(17px,2vw,28px);line-height:1.65}blockquote{border-left:4px solid ${palette.accent};margin:5% 0;padding:1px 20px}
  a{color:${palette.accent}}code{background:#ffffff1c;padding:2px 6px;border-radius:5px}
  </style></head><body>${backgrounds}${rendered}${foregrounds}</body></html>`
})

watch(() => props.markdown, (value) => {
  if (!dirty.value || value === draft.value) draft.value = value
})
watch(() => props.renderedPreviewUrl, (url) => {
  const request = ++previewRequest
  if (!url) {
    displayedPreviewUrl.value = ''
    renderedLoaded.value = false
    renderedFailed.value = false
    previewLoading.value = false
    return
  }
  if (url === displayedPreviewUrl.value && renderedLoaded.value) return
  previewLoading.value = true
  const loader = new Image()
  loader.onload = () => {
    if (request !== previewRequest) return
    displayedPreviewUrl.value = url
    renderedLoaded.value = true
    renderedFailed.value = false
    previewLoading.value = false
  }
  loader.onerror = () => {
    if (request !== previewRequest) return
    renderedFailed.value = !displayedPreviewUrl.value
    previewLoading.value = false
  }
  loader.src = url
}, { immediate: true })

function updateDraft(event: Event) {
  draft.value = (event.target as HTMLTextAreaElement).value
  emit('change', draft.value)
}

onUnmounted(() => {
  previewRequest += 1
})
</script>

<template>
  <div class="slidev-preview">
    <div class="preview-toolbar">
      <div>
        <span class="live-dot" />
        <b>实时预览</b>
        <span v-if="syncing || previewLoading">正在自动同步并编译主题预览</span>
        <span v-else-if="dirty">停止输入后自动同步</span>
        <span v-else-if="renderedLoaded">Slidev 真实主题渲染 · 已同步</span>
        <span v-else-if="renderedPreviewUrl && !renderedFailed">正在准备真实主题预览</span>
        <span v-else>当前页修改会自动同步</span>
      </div>
    </div>

    <div class="preview-stage">
      <img
        v-if="displayedPreviewUrl && !renderedFailed"
        class="rendered-slide"
        :class="{ ready: renderedLoaded }"
        :src="displayedPreviewUrl"
        :alt="`${title || '课件'}的 Slidev 主题预览`"
      />
      <iframe
        v-show="!renderedLoaded"
        :title="title || '课件预览'"
        :srcdoc="srcdoc"
        sandbox=""
        referrerpolicy="no-referrer"
      />
      <div v-if="(dirty || syncing || previewLoading) && renderedLoaded" class="preview-syncing">
        <span />
        {{ dirty && !syncing ? '等待自动同步' : '正在生成新预览' }}
      </div>
    </div>

    <div class="source-editor">
      <div class="editor-tabs">
        <div><b>slides.md</b><span>大纲</span></div>
        <span class="slidev-chip">⚡ Slidev</span>
      </div>
      <div class="editor-body">
        <div class="line-numbers" aria-hidden="true">
          <span v-for="line in Math.max(8, draft.split('\n').length)" :key="line">{{ line }}</span>
        </div>
        <textarea
          :value="draft"
          aria-label="当前页 Markdown 源码"
          spellcheck="false"
          placeholder="# 页面标题&#10;&#10;- 输入课件内容"
          @input="updateDraft"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.slidev-preview{max-width:980px;margin:0 auto;border:1px solid #d9e1dc;border-radius:14px;overflow:hidden;background:#fff;box-shadow:0 18px 46px rgba(26,47,36,.09)}
.preview-toolbar,.preview-toolbar>div,.editor-tabs,.editor-tabs>div{display:flex;align-items:center}
.preview-toolbar{min-height:40px;justify-content:space-between;gap:12px;padding:7px 12px;background:#fff;color:#7b8780;font-size:10px}
.preview-toolbar>div{gap:8px}.preview-toolbar b{color:#35433c;font-size:11px}.live-dot{width:7px;height:7px;border-radius:50%;background:#0eaa79;box-shadow:0 0 0 4px rgba(14,170,121,.1)}
.preview-stage{position:relative;padding:12px 14px 14px;background:linear-gradient(145deg,#f1f8f4,#e8f1ec)}
.preview-stage iframe,.rendered-slide{display:block;width:100%;aspect-ratio:16/9;border:1px solid #d9e2dd;border-radius:8px;background:#fff;box-shadow:0 12px 30px rgba(17,45,31,.12)}.rendered-slide{display:none;object-fit:contain}.rendered-slide.ready{display:block}
.preview-syncing{position:absolute;right:26px;top:24px;display:flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid rgba(255,255,255,.75);border-radius:999px;background:rgba(20,35,28,.72);color:#fff;font-size:9px;box-shadow:0 6px 18px rgba(15,35,25,.16);backdrop-filter:blur(8px)}
.preview-syncing span{width:7px;height:7px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:previewSpin .8s linear infinite}
@keyframes previewSpin{to{transform:rotate(360deg)}}
.source-editor{border-top:1px solid #dfe6e2;background:#fbfdfc}
.editor-tabs{height:40px;justify-content:space-between;padding:0 13px;border-bottom:1px solid #dfe6e2;background:#f4f7f5;color:#8b958f;font-size:10px}
.editor-tabs>div{align-self:stretch;gap:22px}.editor-tabs b{display:flex;align-items:center;border-bottom:2px solid #0eaa79;color:#27342e}.slidev-chip{padding:5px 10px;border:1px solid #b9e2d2;border-radius:999px;background:#e8f7f1;color:#087f5b;font-weight:700}
.editor-body{display:grid;grid-template-columns:38px minmax(0,1fr);min-height:210px}
.line-numbers{display:flex;flex-direction:column;align-items:end;padding:15px 9px 15px 0;border-right:1px solid #e6ebe8;background:#f3f6f4;color:#a5aea9;font:11px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;user-select:none}
textarea{display:block;width:100%;min-height:210px;resize:vertical;border:0;outline:0;padding:15px 18px;background:#fbfdfc;color:#34423b;caret-color:#0eaa79;font:12px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;tab-size:2}
textarea::placeholder{color:#abb4af}
textarea:focus{background:#fff;box-shadow:inset 0 0 0 1px rgba(14,170,121,.18)}
textarea::selection{background:rgba(14,170,121,.18)}
</style>
