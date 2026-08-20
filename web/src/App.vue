<script setup lang="ts">
import { ChatDotRound, FolderOpened } from '@element-plus/icons-vue'
</script>

<template>
  <main class="app-shell">
    <header class="app-header">
      <a class="brand" href="/knowledge" aria-label="Ace RAG 知识库">
        <span class="brand-mark">A</span>
        <span>Ace RAG</span>
      </a>
      <nav class="navigation" aria-label="主导航">
        <el-button text disabled :icon="ChatDotRound">智能问答</el-button>
        <el-button text type="primary" :icon="FolderOpened">知识库</el-button>
      </nav>
    </header>
    <router-view />
  </main>
</template>
