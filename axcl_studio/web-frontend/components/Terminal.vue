<template>
  <div class="terminal-container">
    <div class="terminal-card">
      <div class="terminal-controls">
        <button @click="connectTerminal" :disabled="isConnected" class="connect-btn">
          {{ isConnected ? '已连接' : '连接终端' }}
        </button>
        <button @click="disconnectTerminal" :disabled="!isConnected" class="disconnect-btn">
          断开连接
        </button>
        <button @click="clearTerminal" class="clear-btn">
          清空屏幕
        </button>
      </div>

      <div class="terminal-window" ref="terminalContainer" @contextmenu="showContextMenu"></div>

      <div class="terminal-info">
        <p v-if="isConnected">终端已连接 - 会话ID: {{ sessionId }}</p>
        <p v-else>终端未连接</p>
      </div>
    </div>

    <div 
      v-if="contextMenu.visible && contextMenu.hasSelection" 
      class="context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @click.stop
    >
      <div class="context-menu-item" @click="copySelectedText">
        复制
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'
import { getWsBase } from '../apiBase'

const terminalContainer = ref(null)
const term = ref(null)
const fitAddon = ref(null)
const websocket = ref(null)
const isConnected = ref(false)
const sessionId = ref('')

const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  hasSelection: false
})
const WS_BASE = getWsBase()

const ensureTerminal = () => {
  if (term.value) {
    return
  }

  term.value = new Terminal({
    cursorBlink: true,
    scrollback: 2000,
    convertEol: true,
    fontFamily: '"Fira Code", "Courier New", monospace',
    fontSize: 14,
    theme: {
      background: '#000000',
      foreground: '#ffffff',
      cursor: '#00ff9c'
    }
  })

  fitAddon.value = new FitAddon()
  term.value.loadAddon(fitAddon.value)
  term.value.open(terminalContainer.value)
  fitAddon.value.fit()
  term.value.focus()

  term.value.onData((data) => {
    if (websocket.value && isConnected.value) {
      websocket.value.send(JSON.stringify({
        type: 'input',
        data
      }))
    }
  })
}

const connectTerminal = () => {
  if (isConnected.value || websocket.value) {
    return
  }

  ensureTerminal()

  const wsUrl = `${WS_BASE}/ws/terminal`
  websocket.value = new WebSocket(wsUrl)

  websocket.value.onopen = () => {
    isConnected.value = true
    sessionId.value = `session_${Date.now()}`
    term.value?.reset()
    fitAddon.value?.fit()
    sendResize()
    term.value?.focus()
  }

  websocket.value.onmessage = (event) => {
    const message = JSON.parse(event.data)
    if (message.type === 'output') {
      term.value?.write(message.data)
    }
  }

  websocket.value.onclose = () => {
    isConnected.value = false
    sessionId.value = ''
    term.value?.writeln('\r\n[连接已断开]\r\n')
    websocket.value = null
  }

  websocket.value.onerror = (error) => {
    console.error('终端WebSocket错误:', error)
    term.value?.writeln('\r\n[连接错误]\r\n')
  }
}

const disconnectTerminal = () => {
  if (websocket.value) {
    websocket.value.close()
    websocket.value = null
  }
  isConnected.value = false
  sessionId.value = ''
}

const clearTerminal = () => {
  term.value?.clear()
}

const sendResize = () => {
  if (!websocket.value || !isConnected.value || !term.value) {
    return
  }

  websocket.value.send(JSON.stringify({
    type: 'resize',
    cols: term.value.cols,
    rows: term.value.rows
  }))
}

const handleResize = () => {
  if (fitAddon.value) {
    fitAddon.value.fit()
    sendResize()
  }
}

const showContextMenu = (event) => {
  event.preventDefault()
  const selection = term.value?.getSelection() ?? ''
  contextMenu.value.hasSelection = selection.length > 0
  contextMenu.value.visible = true
  contextMenu.value.x = event.clientX
  contextMenu.value.y = event.clientY
}

const legacyCopy = (text) => {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

const copySelectedText = async () => {
  const selection = term.value?.getSelection() ?? ''
  if (!selection.length) {
    contextMenu.value.visible = false
    return
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(selection)
    } else {
      legacyCopy(selection)
    }
  } catch (error) {
    try {
      legacyCopy(selection)
    } catch (fallbackErr) {
      console.error('复制失败:', fallbackErr)
    }
  } finally {
    contextMenu.value.visible = false
  }
}


const hideContextMenu = () => {
  contextMenu.value.visible = false
}




onMounted(() => {
  ensureTerminal()
  window.addEventListener('resize', handleResize)
  window.addEventListener('click', hideContextMenu)
  // Paste event listener (Ctrl+V)
  if (terminalContainer.value) {
    terminalContainer.value.addEventListener('paste', handlePasteEvent)
  }
})


onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('click', hideContextMenu)
  if (terminalContainer.value) {
    terminalContainer.value.removeEventListener('paste', handlePasteEvent)
  }
  disconnectTerminal()
  term.value?.dispose()
  term.value = null
})

// Paste event handling (Ctrl+V)
const handlePasteEvent = async (event) => {
  event.preventDefault()
  try {
    const text = event.clipboardData?.getData('text')
    if (text && term.value) {
      term.value.write(text)
      if (websocket.value && isConnected.value) {
        websocket.value.send(JSON.stringify({ type: 'input', data: text }))
      }
    }
  } catch (error) {
    console.error('粘贴失败:', error)
  }
}
</script>

<style scoped>
@import 'xterm/css/xterm.css';

.terminal-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  position: relative;
  overflow: hidden;
  color: #e5edff;
}

.terminal-card {
  background: linear-gradient(180deg, rgba(22, 28, 45, 0.95), rgba(16, 21, 34, 0.95));
  border-radius: 14px;
  padding: 20px;
  box-shadow: 0 14px 34px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(59, 130, 246, 0.12);
  margin-bottom: 20px;
  position: relative;
  overflow: hidden;
}

.terminal-controls {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  justify-content: flex-start;
}

button {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.2s;
}

.connect-btn {
  background: linear-gradient(135deg, #2563eb, #10b981);
  color: white;
}

.connect-btn:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
}

.connect-btn:disabled {
  background: #475569;
  cursor: not-allowed;
  opacity: 0.6;
}

.disconnect-btn {
  background: rgba(239, 68, 68, 0.2);
  color: #fca5a5;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.disconnect-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.3);
}

.disconnect-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.clear-btn {
  background: rgba(255, 255, 255, 0.1);
  color: #e5edff;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.clear-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.terminal-window {
  background: #000;
  border-radius: 8px;
  height: 600px;
  padding: 16px;
  position: relative;
  box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.terminal-window :deep(.xterm-viewport) {
  border-radius: 4px;
}

.terminal-info {
  margin-top: 20px;
  padding: 12px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  text-align: center;
  color: #94a3b8;
  font-size: 0.9rem;
}

.context-menu {
  position: fixed;
  background: #1e293b;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  z-index: 2000;
  min-width: 120px;
  padding: 4px 0;
}

.context-menu-item {
  padding: 8px 16px;
  color: #e5edff;
  font-size: 14px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s;
}

.context-menu-item:hover {
  background: rgba(255, 255, 255, 0.1);
}
</style>