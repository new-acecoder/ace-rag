<script setup lang="ts">
import { ChatDotRound, FolderOpened } from '@element-plus/icons-vue'
</script>

<template>
  <main class="app-shell">
    <header class="app-header">
      <router-link class="brand" to="/chat" aria-label="Ace RAG 智能问答">
        <span class="brand-mark">A</span>
        <span>Ace RAG</span>
      </router-link>
      <nav class="navigation" aria-label="主导航">
        <el-button text :icon="ChatDotRound" :class="{ 'is-current': $route.path === '/chat' }" @click="$router.push('/chat')">
          智能问答
        </el-button>
        <el-button text :icon="FolderOpened" :class="{ 'is-current': $route.path === '/knowledge' }" @click="$router.push('/knowledge')">
          知识库
        </el-button>
      </nav>
    </header>
    <router-view />
  </main>
</template>
