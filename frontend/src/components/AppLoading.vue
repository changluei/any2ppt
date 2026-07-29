<!-- 页面级加载骨架，避免各页面复制不同的 loading 结构。 -->
<template>
  <div class="empty-wrap">
    <el-skeleton :rows="4" animated />
    <p class="muted">正在加载，请稍候…</p>
  </div>
</template>
