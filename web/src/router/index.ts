import { createRouter, createWebHistory } from 'vue-router'

import KnowledgeView from '@/views/KnowledgeView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/knowledge' },
    { path: '/knowledge', component: KnowledgeView },
  ],
})
