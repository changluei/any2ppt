<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isFullScreen = computed(() => route.path.startsWith('/workbench') || Boolean(route.meta.fullScreen))
const navItems = [
  { label: '创建', path: '/create' },
  { label: '我的演示', path: '/projects' },
  { label: '知识库', path: '/knowledge' },
]
</script>

<template>
  <router-view v-if="isFullScreen" />
  <div v-else class="site-shell">
    <header class="site-header">
      <router-link to="/create" class="brand" aria-label="Any2PPT 首页">
        <span class="brand-mark" aria-hidden="true">
          <i /><i /><i />
        </span>
        <strong>Any2PPT</strong>
        <span class="beta">BETA</span>
      </router-link>

      <nav class="site-nav" aria-label="主导航">
        <router-link v-for="item in navItems" :key="item.path" :to="item.path">
          {{ item.label }}
        </router-link>
      </nav>
    </header>
    <main class="site-main">
      <router-view />
    </main>
  </div>
</template>
