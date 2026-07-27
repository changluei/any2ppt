<script setup lang="ts">
import type { ThemeDescriptor } from '../types'

defineProps<{
  theme: ThemeDescriptor
}>()
</script>

<template>
  <div class="theme-visual" :style="{ '--theme-accent': theme.palette.accent, '--theme-bg': theme.palette.background, '--theme-text': theme.palette.text }">
    <img v-if="theme.preview_url" :src="theme.preview_url" :alt="`${theme.name} 主题预览`" />
    <div v-else class="generated-preview" :class="`preview-${theme.id}`">
      <div class="preview-topline"><span>01 / ANY2PPT</span><span>SLIDEV</span></div>
      <div class="preview-content">
        <span class="preview-kicker">A BETTER WAY TO PRESENT</span>
        <strong>{{ theme.name }}</strong>
        <small>{{ theme.description }}</small>
      </div>
      <div class="preview-shape" />
      <span class="preview-page">01</span>
    </div>
  </div>
</template>

<style scoped>
.theme-visual{width:100%;height:100%;overflow:hidden;background:var(--theme-bg)}
.theme-visual>img{display:block;width:100%;height:100%;object-fit:cover}
.generated-preview{position:relative;width:100%;height:100%;min-height:180px;overflow:hidden;padding:7% 7.5%;background:var(--theme-bg);color:var(--theme-text);font-family:Inter,"PingFang SC",sans-serif}
.preview-topline{position:relative;z-index:2;display:flex;justify-content:space-between;font-size:8px;font-weight:700;letter-spacing:1.4px;opacity:.58}
.preview-content{position:absolute;z-index:2;left:7.5%;top:39%;width:62%;display:grid;gap:7px}
.preview-kicker{color:var(--theme-accent);font-size:8px;font-weight:800;letter-spacing:1px}
.preview-content strong{font-family:"Songti SC",STSong,Georgia,serif;font-size:clamp(23px,3vw,42px);line-height:1}
.preview-content small{max-width:300px;font-size:9px;line-height:1.45;opacity:.62}
.preview-shape{position:absolute;right:-2%;bottom:-12%;width:38%;aspect-ratio:1;border-radius:50%;background:var(--theme-accent);opacity:.9}
.preview-page{position:absolute;left:7.5%;bottom:7%;font-size:9px;font-weight:700}
.preview-academic{background:#111827;color:#f8fafc}.preview-academic .preview-shape{right:6%;bottom:10%;border-radius:3px;background:transparent;border:1px solid #f8fafc;opacity:.25;transform:rotate(8deg)}.preview-academic .preview-content strong{font-family:Inter,"PingFang SC",sans-serif;font-weight:300}
.preview-dracula{background:linear-gradient(135deg,#282a36,#171820);color:#f8f8f2}.preview-dracula .preview-shape{right:7%;bottom:12%;width:27%;border-radius:18px;background:linear-gradient(135deg,#bd93f9,#ff79c6)}.preview-dracula .preview-kicker{color:#50fa7b}
.preview-neversink{background:#fffdf5;color:#272822}.preview-neversink::before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent 49.7%,rgba(30,40,34,.06) 50%,transparent 50.3%)}.preview-neversink .preview-shape{right:-6%;bottom:-20%;width:46%;border-radius:22% 78% 55% 45%;background:#ffcb45}.preview-neversink .preview-content strong{font-weight:700}
.preview-nord{background:linear-gradient(145deg,#2e3440,#3b4252);color:#eceff4}.preview-nord .preview-shape{right:6%;bottom:11%;width:29%;border-radius:10px;background:#88c0d0;transform:rotate(-7deg)}.preview-nord .preview-kicker{color:#a3be8c}
.preview-light-icons{background:#f8fbff;color:#192235}.preview-light-icons::before,.preview-light-icons::after{content:"";position:absolute;border-radius:50%;filter:blur(1px)}.preview-light-icons::before{right:-5%;top:-18%;width:45%;aspect-ratio:1;background:#dbeafe}.preview-light-icons::after{right:12%;bottom:-24%;width:34%;aspect-ratio:1;background:#ede9fe}.preview-light-icons .preview-shape{right:12%;bottom:18%;width:20%;border-radius:20px;background:linear-gradient(145deg,#60a5fa,#8b5cf6);transform:rotate(12deg)}
</style>
