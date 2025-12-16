<template>
  <div class="fm-shell">
    <div class="fm-card">
      <div class="fm-header">
        <div class="path-row">
          <span class="path-label">当前位置:</span>
          <span class="path-value">{{ isTrashView ? '回收站' : (currentPath ? '/root/file_storage/' + currentPath : '/root/file_storage') }}</span>
          <!-- <button class="ghost-btn" @click="toggleTrash">{{ isTrashView ? '返回文件' : '查看回收站' }}</button> -->
          <button class="ghost-btn" @click="goUp" :disabled="isTrashView || !currentPath">上一级</button>
          <button class="ghost-btn" @click="refresh">刷新</button>
          <span class="total-size" v-if="totalSize !== null">当前目录总大小：{{ formatSize(totalSize) }}</span>
        </div>
        <div class="header-actions">
          <div class="upload-group">
            <button class="ghost-btn" @click="createDir" :disabled="isTrashView">新建目录</button>
            <label class="upload-btn" :class="{ disabled: isTrashView }">
              上传文件
              <input type="file" @change="handleUpload" :disabled="isTrashView" />
            </label>
            <div v-if="uploading" class="upload-progress">
              <div class="bar" :style="{ width: uploadPercent + '%' }"></div>
              <span class="upload-text">{{ uploadPercent.toFixed(0) }}%</span>
            </div>
          </div>
          <button class="danger-btn" v-if="isTrashView" @click="clearTrash" :disabled="loading">清空回收站</button>
        </div>
      </div>

      <p v-if="error" class="error-text">{{ error }}</p>

      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>大小</th>
              <th>修改时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="5" class="muted">正在加载...</td>
            </tr>
            <tr v-else-if="!files.length">
              <td colspan="5" class="muted">该目录下暂无文件</td>
            </tr>
            <tr v-else v-for="item in files" :key="item.name">
              <td>
                <button v-if="!isTrashView && item.is_dir" class="link-btn" @click="enterDir(item.name)">
                  📁 {{ item.name }}
                </button>
                <span v-else>📄 {{ item.name }}</span>
              </td>
              <td>{{ item.is_dir ? '目录' : '文件' }}</td>
              <td>{{ item.is_dir ? '-' : formatSize(item.size) }}</td>
              <td>{{ formatTime(item.mtime) }}</td>
              <td class="actions">
                <button v-if="!isTrashView && !item.is_dir" class="ghost-btn" @click="downloadFile(item.name)">下载</button>
                <button v-if="isTrashView" class="ghost-btn" @click="restoreItem(item)">恢复</button>
                <button v-if="!isTrashView" class="danger-btn" @click="deleteItem(item)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
import { getApiBase } from '../apiBase'

const API_BASE = getApiBase()
const files = ref([])
const loading = ref(false)
const error = ref('')
const currentPath = ref('')
const isTrashView = ref(false)
const totalSize = ref(null)
const uploading = ref(false)
const uploadPercent = ref(0)

const joinPath = (name) => (currentPath.value ? `${currentPath.value}/${name}` : name)

const fetchTotalSize = async () => {
  try {
    const targetPath = isTrashView.value ? '.trash' : currentPath.value
    const res = await axios.get(`${API_BASE}/files/size`, {
      params: { path: targetPath }
    })
    totalSize.value = res.data?.size_bytes ?? null
  } catch (err) {
    totalSize.value = null
  }
}

const refresh = async () => {
  loading.value = true
  error.value = ''
  try {
    if (isTrashView.value) {
      const res = await axios.get(`${API_BASE}/files/trash`)
      files.value = Array.isArray(res.data) ? res.data : []
    } else {
      const res = await axios.get(`${API_BASE}/files`, {
        params: { path: currentPath.value }
      })
      files.value = Array.isArray(res.data) ? res.data : []
    }
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '加载失败'
  } finally {
    loading.value = false
    fetchTotalSize()
  }
}

const enterDir = (name) => {
  if (isTrashView.value) return
  currentPath.value = joinPath(name)
  refresh()
}

const goUp = () => {
  if (isTrashView.value || !currentPath.value) return
  const parts = currentPath.value.split('/').filter(Boolean)
  parts.pop()
  currentPath.value = parts.join('/')
  refresh()
}

const createDir = async () => {
  if (isTrashView.value) return
  const name = prompt('请输入文件夹名称:')
  if (!name) return
  
  try {
    // Use URLSearchParams to ensure correct passing of empty string paths
    const params = new URLSearchParams()
    params.append('path', currentPath.value || '')
    params.append('name', name)
    
    await axios.post(`${API_BASE}/files/mkdir`, params)
    await refresh()
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '创建失败'
  }
}

const handleUpload = async (event) => {
  if (isTrashView.value) return
  const file = event.target.files?.[0]
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  form.append('path', currentPath.value || '')
  try {
    uploading.value = true
    uploadPercent.value = 0
    await axios.post(`${API_BASE}/files/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (evt) => {
        if (evt.total) {
          uploadPercent.value = Math.min(100, (evt.loaded / evt.total) * 100)
        }
      }
    })
    await refresh()
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '上传失败'
  } finally {
    uploading.value = false
    uploadPercent.value = 0
    event.target.value = ''
  }
}

const downloadFile = (name) => {
  const path = joinPath(name)
  const url = `${API_BASE}/files/download?path=${encodeURIComponent(path)}`
  window.open(url, '_blank')
}

const deleteItem = async (item) => {
  if (isTrashView.value) return
  const path = joinPath(item.name)
  try {
    await axios.delete(`${API_BASE}/files`, { params: { path } })
    await refresh()
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '删除失败'
  }
}

const restoreItem = async (item) => {
  if (!isTrashView.value) return
  try {
    await axios.post(`${API_BASE}/files/trash/restore`, null, { params: { name: item.name } })
    await refresh()
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '恢复失败'
  }
}

const clearTrash = async () => {
  if (!confirm('确定要清空回收站吗？此操作不可恢复')) return
  try {
    await axios.delete(`${API_BASE}/files/trash/clear`)
    await refresh()
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '清空失败'
  }
}

const formatSize = (size) => {
  if (!size) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let n = size
  let idx = 0
  while (n >= 1024 && idx < units.length - 1) {
    n /= 1024
    idx += 1
  }
  return `${n.toFixed(1)} ${units[idx]}`
}

const formatTime = (ts) => {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString()
}

const toggleTrash = () => {
  isTrashView.value = !isTrashView.value
  if (isTrashView.value) {
    currentPath.value = ''
  }
  refresh()
}

watch(isTrashView, () => {
  error.value = ''
})

onMounted(() => {
  refresh()
})
</script>

<style scoped>
.fm-shell {
  padding: 20px;
  color: #e5edff;
  position: relative;
}

.fm-card {
  background: linear-gradient(180deg, rgba(22, 28, 45, 0.95), rgba(16, 21, 34, 0.95));
  border-radius: 14px;
  padding: 20px;
  box-shadow: 0 14px 34px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(59, 130, 246, 0.12);
  margin-bottom: 20px;
  position: relative;
  overflow: hidden;
}

.fm-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}

.path-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.path-label {
  font-weight: 700;
  color: #a5b4fc;
}

.path-value {
  color: #f8fafc;
  font-family: 'Fira Code', monospace;
}

.total-size {
  color: #cbd5f5;
  font-size: 14px;
  margin-left: 12px;
}

.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.upload-btn {
  background: linear-gradient(135deg, #2563eb, #10b981);
  color: #0b0f1d;
  padding: 6px 12px;
  border-radius: 8px;
  font-weight: 700;
  cursor: pointer;
  border: none;
  position: relative;
  overflow: hidden;
}

.upload-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-btn input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.upload-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.upload-progress {
  position: relative;
  width: 140px;
  height: 8px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  overflow: hidden;
}

.upload-progress .bar {
  height: 100%;
  background: linear-gradient(135deg, #34d399, #22d3ee);
  transition: width 0.15s ease;
}

.upload-text {
  font-size: 12px;
  color: #cbd5f5;
}

.table-container {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: 12px;
  text-align: left;
}

th {
  background: rgba(255, 255, 255, 0.04);
  color: #cfd8ff;
  font-weight: 700;
}

td {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.muted {
  color: #94a3b8;
  text-align: center;
}

.link-btn {
  background: none;
  border: none;
  color: #60a5fa;
  cursor: pointer;
  padding: 0;
  font-weight: 700;
}

.ghost-btn {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #e5edff;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
}

.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.danger-btn {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.5);
  color: #fecdd3;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
}

.error-text {
  color: #fecdd3;
  margin-bottom: 12px;
}
</style>
