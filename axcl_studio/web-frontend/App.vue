

<template>
  <div class="app-shell">
    <header class="app-header">
      <nav class="app-nav">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          class="nav-btn"
          :class="{ active: activeTab === tab.value }"
          @click="activeTab = tab.value"
        >
          {{ tab.label }}
        </button>
      </nav>
    </header>
    <main class="app-main">
      <keep-alive>
        <DashboardView v-if="activeTab === 'dashboard'" />
        <FileManager v-else-if="activeTab === 'files'" />
        <Terminal v-else-if="activeTab === 'terminal'" />
        <YoloRunner v-else-if="activeTab === 'yolo'" />
      </keep-alive>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import DashboardView from './components/DashboardView.vue'
import FileManager from './components/FileManager.vue'
import Terminal from './components/Terminal.vue'
import YoloRunner from './components/YoloRunner.vue'

const tabs = [
  { value: 'dashboard', label: '状态总览' },
  { value: 'files', label: '文件传输' },
  { value: 'terminal', label: '虚拟终端' },
  { value: 'yolo', label: 'YOLOv5' }
]

const activeTab = ref('dashboard')
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: radial-gradient(circle at 20% 20%, rgba(58, 121, 255, 0.2), transparent 30%),
              radial-gradient(circle at 80% 0%, rgba(16, 185, 129, 0.16), transparent 32%),
              linear-gradient(180deg, #0a0f1c 0%, #060912 100%);
  padding-bottom: 60px;
  position: relative;
  overflow: hidden;
}

.app-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 32px 16px 24px;
}

.app-nav {
  display: flex;
  gap: 12px;
}

.nav-btn {
  padding: 10px 20px;
  border: 1px solid rgba(99, 179, 237, 0.5);
  border-radius: 22px;
  background: rgba(37, 99, 235, 0.15);
  color: #e5edff;
  font-weight: 700;
  cursor: pointer;
  letter-spacing: 0.3px;
  backdrop-filter: blur(6px);
  transition: all 0.2s ease;
}

.nav-btn.active {
  background: linear-gradient(135deg, #2563eb, #10b981);
  color: #0b0f1d;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.45), 0 0 0 1px rgba(16, 185, 129, 0.4);
}

.nav-btn:not(.active):hover {
  background: rgba(59, 130, 246, 0.28);
  border-color: rgba(16, 185, 129, 0.55);
}

.app-main {
  max-width: 1080px;
  margin: 0 auto;
  padding: 0 16px;
}
</style>
