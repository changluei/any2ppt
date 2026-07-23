<script setup lang="ts">
import { computed, ref } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const props = defineProps<{ markdown: string; title?: string }>()
const sourceVisible = ref(false)
const parser = new MarkdownIt({ html: false, linkify: true, breaks: true })
const srcdoc = computed(() => {
  const rendered = DOMPurify.sanitize(parser.render(props.markdown || ''))
  const title = DOMPurify.sanitize(props.title || '课件预览')
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${title}</title><style>
  *{box-sizing:border-box}body{margin:0;min-height:100vh;padding:8% 9%;font-family:Inter,"PingFang SC",sans-serif;
  color:#f8fbff;background:radial-gradient(circle at 80% 10%,#2d6397,#142b4d 52%,#0b1930)}
  h1{font-size:clamp(32px,5vw,64px);line-height:1.15;margin:0 0 5%}h2{font-size:clamp(24px,3vw,42px)}
  p,li{font-size:clamp(17px,2vw,28px);line-height:1.65}blockquote{border-left:4px solid #6be5c3;margin:5% 0;padding:1px 20px;color:#c9f7e9}
  a{color:#9bd6ff}code{background:#ffffff1c;padding:2px 6px;border-radius:5px}
  </style></head><body>${rendered}</body></html>`
})
</script>

<template>
  <div class="slidev-preview">
    <div class="preview-toolbar">
      <span>Slidev 兼容安全预览</span>
      <el-button link @click="sourceVisible = !sourceVisible">
        {{ sourceVisible ? '返回预览' : '查看 Markdown 源码' }}
      </el-button>
    </div>
    <pre v-if="sourceVisible" class="markdown-source">{{ markdown }}</pre>
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
.preview-toolbar{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#f6f8fc;color:#67758d;font-size:12px}
iframe{display:block;width:100%;aspect-ratio:16/9;border:0;background:#102444}
.markdown-source{margin:0;min-height:320px;padding:20px;overflow:auto;white-space:pre-wrap;background:#111c2e;color:#dceaff;font:14px/1.65 ui-monospace,SFMono-Regular,monospace}
</style>
