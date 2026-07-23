<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import type { SlideImagePlacement, ThemeDescriptor } from '../types'

const props = withDefaults(defineProps<{
  markdown: string
  title?: string
  saving?: boolean
  images?: SlideImagePlacement[]
  imageBaseUrl?: string
  themePalette?: ThemeDescriptor['palette']
}>(), {
  title: '',
  saving: false,
  images: () => [],
  imageBaseUrl: '',
  themePalette: () => ({
    background: '#142b4d',
    surface: '#0b1930',
    text: '#f8fbff',
    accent: '#6be5c3',
  }),
})
const emit = defineEmits<{
  save: [markdown: string]
  'dirty-change': [dirty: boolean]
}>()

const sourceVisible = ref(false)
const draft = ref(props.markdown)
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
  draft.value = value
})
watch(dirty, (value) => emit('dirty-change', value), { immediate: true })
</script>

<template>
  <div class="slidev-preview">
    <div class="preview-toolbar">
      <div>
        <b>{{ sourceVisible ? 'Markdown 实时编辑' : '课件预览' }}</b>
        <span v-if="sourceVisible">输入后右侧立即重新编译</span>
      </div>
      <div class="toolbar-actions">
        <span v-if="dirty" class="unsaved">未保存</span>
        <el-button
          v-if="dirty"
          type="primary"
          size="small"
          :loading="saving"
          :disabled="saving || !draft.trim()"
          @click="emit('save', draft)"
        >
          保存修改
        </el-button>
        <el-button link @click="sourceVisible = !sourceVisible">
          {{ sourceVisible ? '返回全屏预览' : '编辑 Markdown 源码' }}
        </el-button>
      </div>
    </div>

    <div v-if="sourceVisible" class="source-workspace">
      <div class="source-editor">
        <div class="editor-caption"><span>当前页源码</span><span>{{ draft.length }} 字符</span></div>
        <textarea
          v-model="draft"
          aria-label="当前页 Markdown 源码"
          spellcheck="false"
          placeholder="# 页面标题&#10;&#10;- 输入课件内容"
        />
      </div>
      <div class="live-preview">
        <div class="editor-caption"><span>实时编译结果</span><span>LIVE</span></div>
        <iframe
          :title="`${title || '课件'}实时预览`"
          :srcdoc="srcdoc"
          sandbox=""
          referrerpolicy="no-referrer"
        />
      </div>
    </div>
    <iframe
      v-else
      :title="title || '课件预览'"
      :srcdoc="srcdoc"
      sandbox=""
      referrerpolicy="no-referrer"
    />
  </div>
</template>

<style scoped>
.slidev-preview{border:1px solid #dce3ee;border-radius:12px;overflow:hidden;background:#fff}
.preview-toolbar,.preview-toolbar>div,.toolbar-actions,.editor-caption{display:flex;align-items:center}
.preview-toolbar{min-height:44px;justify-content:space-between;gap:12px;padding:8px 12px;background:#f6f8fc;color:#67758d;font-size:12px}
.preview-toolbar>div,.toolbar-actions{gap:10px}.preview-toolbar b{color:#38445b;font-size:13px}.unsaved{color:#d97706}
.source-workspace{display:grid;grid-template-columns:minmax(320px,42%) minmax(0,58%);min-height:470px}
.source-editor,.live-preview{display:flex;min-width:0;flex-direction:column}.source-editor{border-right:1px solid #dce3ee;background:#111c2e}
.editor-caption{height:34px;justify-content:space-between;padding:0 12px;background:#1a2940;color:#aebed2;font-size:11px;letter-spacing:.02em}
.live-preview .editor-caption{background:#e9edf5;color:#68748a}.live-preview .editor-caption span:last-child{color:#3e8c68;font-weight:700}
textarea{display:block;flex:1;width:100%;min-height:436px;resize:none;border:0;outline:0;padding:18px;background:#111c2e;color:#dceaff;font:14px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;tab-size:2}
iframe{display:block;width:100%;aspect-ratio:16/9;border:0;background:#102444}.live-preview iframe{flex:1;aspect-ratio:auto;min-height:436px}
@media(max-width:980px){.source-workspace{grid-template-columns:1fr}.source-editor{border-right:0;border-bottom:1px solid #dce3ee}.source-workspace textarea,.live-preview iframe{min-height:360px}}
</style>
