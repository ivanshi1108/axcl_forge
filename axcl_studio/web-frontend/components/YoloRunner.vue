<template>
  <div class="fm-shell">
    <div class="form-card">
      <form class="yolo-form" @submit.prevent="handleSubmit">
        <label class="form-field">
          <span>模型路径</span>
          <input v-model="form.modelPath" type="text" :placeholder="defaultModelPlaceholder" />
        </label>

        <label class="form-field">
          <span>推理引擎</span>
          <select v-model="form.provider" @change="handleProviderChange">
            <option value="AUTO">AUTO</option>
            <option v-for="item in providerOptions" :key="item" :value="item">{{ item }}</option>
          </select>
          <small v-if="providers.error" class="provider-hint">{{ providers.error }}</small>
        </label>

        <label class="form-field" v-if="form.provider === axclrtProvider">
          <span>Device ID</span>
          <input v-model.number="form.deviceId" type="number" min="0" step="1" />
        </label>

        <label class="form-field">
          <span>重复次数</span>
          <input v-model.number="form.repeat" type="number" min="1" max="10000" step="1" />
        </label>

        <label class="form-field">
          <span>输入图片</span>
          <input type="file" accept="image/*" @change="handleFileChange" required />
        </label>

        <button class="submit-btn" type="submit" :disabled="loading">{{ loading ? '运行中...' : '开始推理' }}</button>
      </form>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="result" class="table-card">
      <h2>推理结果</h2>
      <p class="metric">耗时: 最小 {{ result.metrics.min_ms.toFixed(2) }} ms · 最大 {{ result.metrics.max_ms.toFixed(2) }} ms · 平均 {{ result.metrics.avg_ms.toFixed(2) }} ms</p>
      <p class="metric">检测数量: {{ result.detections.length }}</p>
      <p v-if="result.model_path" class="metric">使用模型: {{ result.model_path }}</p>
      <p v-if="result.provider" class="metric">使用引擎: {{ result.provider }}</p>
      <div class="preview" ref="previewContainer">
        <img ref="imageRef" :src="imageUrl" alt="推理输出" @load="onImageLoad" v-if="imageUrl" />
        <canvas ref="canvasRef" class="overlay-canvas"></canvas>
      </div>
      <div v-if="result.detections.length" class="detections">
        <h3>检测框</h3>
        <table>
          <thead>
            <tr>
              <th>类别</th>
              <th>分数</th>
              <th>坐标</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in result.detections" :key="idx">
              <td>{{ item.label }}</td>
              <td>{{ (item.score * 100).toFixed(2) }}%</td>
              <td>{{ `[${item.x1}, ${item.y1}, ${item.x2}, ${item.y2}]` }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="result.logs.length" class="logs">
        <div class="logs-header" @click="showLogs = !showLogs">
          <h3>日志输出</h3>
          <span class="toggle-icon">{{ showLogs ? '▼' : '▶' }}</span>
        </div>
        <pre v-if="showLogs">{{ result.logs.join('\n') }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, computed, nextTick } from 'vue'
import axios from 'axios'
import { getApiBase } from '../apiBase'

const form = reactive({
  modelPath: '',
  provider: 'AUTO',
  deviceId: 0,
  repeat: 1
})
const fileRef = ref(null)
const imageUrl = ref('')
const imageRef = ref(null)
const canvasRef = ref(null)
const showLogs = ref(false)
const loading = ref(false)
const error = ref('')
const result = ref(null)
const providers = ref({ available: [], all: [], error: null, default_model_path: '', default_provider: '' })
const providerTouched = ref(false)
const API_BASE = getApiBase()

const axclrtProvider = 'AXCLRTExecutionProvider'

const providerOptions = computed(() => {
  const list = (providers.value.available && providers.value.available.length)
    ? providers.value.available
    : providers.value.all
  return (list || []).filter(item => item !== 'AUTO')
})

const defaultModelPath = computed(() => providers.value.default_model_path || '')
const defaultModelPlaceholder = computed(() => defaultModelPath.value || '请输入模型路径（可留空）')
const defaultProvider = computed(() => providers.value.default_provider || 'AUTO')

const ensureProviderSelection = () => {
  if (providerTouched.value) return
  const availableList = providers.value.available || []
  const preferred = defaultProvider.value
  if (preferred && preferred !== 'AUTO' && availableList.includes(preferred)) {
    form.provider = preferred
    return
  }
  if (availableList.length) {
    form.provider = availableList[0]
    return
  }
  form.provider = 'AUTO'
}

const fetchProviders = async () => {
  try {
    const res = await axios.get(`${API_BASE}/providers`)
    providers.value = {
      available: res.data.available || [],
      all: res.data.all || [],
      error: res.data.error || null,
      default_model_path: res.data.default_model_path || '',
      default_provider: res.data.default_provider || ''
    }
    ensureProviderSelection()
  } catch (e) {
    providers.value = { available: [], all: [], error: '获取推理引擎信息失败', default_model_path: '', default_provider: '' }
    ensureProviderSelection()
  }
}

const handleFileChange = (event) => {
  const [file] = event.target.files || []
  fileRef.value = file || null
  if (file) {
    imageUrl.value = URL.createObjectURL(file)
    result.value = null
    // Clear canvas
    if (canvasRef.value) {
      const ctx = canvasRef.value.getContext('2d')
      ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)
    }
  } else {
    imageUrl.value = ''
  }
}

const onImageLoad = () => {
  if (!imageRef.value || !canvasRef.value) return
  const img = imageRef.value
  const canvas = canvasRef.value
  canvas.width = img.naturalWidth
  canvas.height = img.naturalHeight
  
  // After image loads, redraw if there are results
  if (result.value && result.value.detections) {
    drawDetections(result.value.detections)
  }
}

const drawDetections = (detections) => {
  if (!canvasRef.value || !detections) return
  const ctx = canvasRef.value.getContext('2d')
  ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)
  
  // Color list
  const colors = ['#FF3838', '#FF9D97', '#FF701F', '#FFB21D', '#CFD231', '#48F90A', '#92CC17', '#3DDB86', '#1A9334', '#00D4BB',
                  '#2C99A8', '#00C2FF', '#344593', '#6473FF', '#0018EC', '#8438FF', '#520085', '#CB38FF', '#FF95C8', '#FF37C7']

  detections.forEach((det, i) => {
    const color = colors[i % colors.length]
    const { x1, y1, x2, y2, label, score } = det
    const w = x2 - x1
    const h = y2 - y1
    
    ctx.lineWidth = 3
    ctx.strokeStyle = color
    ctx.strokeRect(x1, y1, w, h)
    
    // Draw label background
    ctx.font = 'bold 16px Arial'
    const text = `${label} ${(score * 100).toFixed(1)}%`
    const textMetrics = ctx.measureText(text)
    const textW = textMetrics.width
    const textH = 20
    
    ctx.fillStyle = color
    ctx.fillRect(x1, y1 - textH, textW + 8, textH)
    
    // Draw text
    ctx.fillStyle = '#FFFFFF'
    ctx.fillText(text, x1 + 4, y1 - 4)
  })
}

const handleProviderChange = () => {
  providerTouched.value = true
}

const buildDetections = (items) => {
  return (items || []).map(entry => ({
    label: entry.label,
    score: entry.score,
    x1: Math.round(entry.box[0]),
    y1: Math.round(entry.box[1]),
    x2: Math.round(entry.box[2]),
    y2: Math.round(entry.box[3])
  }))
}

const preprocessImage = async (file) => {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const targetSize = 640
      const canvas = document.createElement('canvas')
      canvas.width = targetSize
      canvas.height = targetSize
      const ctx = canvas.getContext('2d')
      
      // Fill gray background
      ctx.fillStyle = 'rgb(114, 114, 114)'
      ctx.fillRect(0, 0, targetSize, targetSize)
      
      // Calculate scale ratio (Letterbox)
      const scale = Math.min(targetSize / img.width, targetSize / img.height)
      const w = Math.round(img.width * scale)
      const h = Math.round(img.height * scale)
      const x = Math.round((targetSize - w) / 2)
      const y = Math.round((targetSize - h) / 2)
      
      // Draw image
      ctx.drawImage(img, x, y, w, h)
      
      // Get pixel data
      const imageData = ctx.getImageData(0, 0, targetSize, targetSize)
      const data = imageData.data // RGBA
      
      // Convert to RGB Uint8Array
      const rgbData = new Uint8Array(targetSize * targetSize * 3)
      for (let i = 0, j = 0; i < data.length; i += 4, j += 3) {
        rgbData[j] = data[i]     // R
        rgbData[j + 1] = data[i + 1] // G
        rgbData[j + 2] = data[i + 2] // B
      }
      
      resolve({
        rgbData,
        originWidth: img.width,
        originHeight: img.height
      })
    }
    img.onerror = reject
    img.src = URL.createObjectURL(file)
  })
}

const handleSubmit = async () => {
  if (!fileRef.value) {
    error.value = '请先选择图片文件'
    return
  }
  error.value = ''
  loading.value = true
  result.value = null
  
  // Clear canvas
  if (canvasRef.value) {
    const ctx = canvasRef.value.getContext('2d')
    ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)
  }

  try {
    // Frontend preprocessing
    const { rgbData, originWidth, originHeight } = await preprocessImage(fileRef.value)
    
    const formData = new FormData()
    if (form.modelPath && form.modelPath.trim().length) {
      formData.append('model_path', form.modelPath.trim())
    }
    formData.append('provider', form.provider)
    formData.append('repeat', String(form.repeat))
    formData.append('device_id', String(form.deviceId))
    
    // Send raw data
    const blob = new Blob([rgbData], { type: 'application/octet-stream' })
    formData.append('image', blob, 'raw_image.bin')
    formData.append('is_raw', 'true')
    formData.append('origin_width', String(originWidth))
    formData.append('origin_height', String(originHeight))

    const response = await axios.post(`${API_BASE}/yolov5/run`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    const data = response.data
    if (!data.success) {
      throw new Error(data.error || '推理失败')
    }
    const detections = buildDetections(data.detections)
    result.value = {
      metrics: data.metrics,
      detections: detections,
      logs: data.logs || [],
      model_path: data.model_path || '',
      provider: data.provider || form.provider
    }
    
    await nextTick()
    // If image has already loaded, draw directly
    if (imageRef.value && imageRef.value.complete) {
      onImageLoad()
    }
    
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '推理失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchProviders()
})
</script>

<style scoped>
.fm-shell {
  padding: 20px;
  color: #e5edff;
}

.fm-header {
  margin-bottom: 20px;
}

.fm-header h1 {
  margin: 0;
  color: #e5edff;
  font-size: 1.5rem;
}

.form-card,
.table-card {
  background: linear-gradient(180deg, rgba(22, 28, 45, 0.95), rgba(16, 21, 34, 0.95));
  border-radius: 14px;
  padding: 20px;
  box-shadow: 0 14px 34px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(59, 130, 246, 0.12);
  margin-bottom: 20px;
  position: relative;
  overflow: hidden;
}

.yolo-form {
  display: grid;
  gap: 16px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-weight: 600;
  color: #e5edff;
}

.form-field input,
.form-field select {
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  font-size: 1rem;
  background: rgba(0, 0, 0, 0.2);
  color: #e5edff;
}

.form-field input::placeholder {
  color: rgba(229, 237, 255, 0.4);
}

.field-hint {
  color: #94a3b8;
  font-size: 0.85rem;
}

.provider-hint {
  color: #f87171;
  font-size: 0.85rem;
}

.submit-btn {
  padding: 10px 16px;
  border: none;
  border-radius: 6px;
  background: linear-gradient(135deg, #2563eb, #10b981);
  color: #fff;
  cursor: pointer;
  font-size: 1rem;
  transition: opacity 0.2s;
  font-weight: 600;
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.submit-btn:not(:disabled):hover {
  opacity: 0.9;
}

.error-text {
  color: #f87171;
  text-align: center;
  margin-bottom: 16px;
}

.table-card h2,
.table-card h3 {
  color: #e5edff;
  margin-top: 0;
}

.metric {
  margin: 8px 0;
  color: #cbd5e1;
}

.preview {
  margin: 16px auto;
  max-width: 100%;
  text-align: center;
  position: relative;
  display: block;
  width: fit-content;
}

.preview img {
  max-width: 100%;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  display: block;
}

.overlay-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.detections {
  margin-top: 16px;
}

.detections table {
  width: 100%;
  border-collapse: collapse;
}

.detections th,
.detections td {
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  text-align: center;
  font-size: 0.95rem;
  color: #e5edff;
}

.detections th {
  background: rgba(255, 255, 255, 0.05);
}

.logs {
  margin-top: 16px;
  background: rgba(0, 0, 0, 0.3);
  color: #e0f2ff;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
}

.logs-header h3 {
  margin: 0;
  font-size: 1rem;
}

.toggle-icon {
  font-size: 1rem;
  color: #cbd5e1;
}

.logs pre {
  margin-top: 10px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Fira Code', monospace;
  font-size: 0.8rem;
  max-height: 300px;
  overflow-y: auto;
}
</style>
