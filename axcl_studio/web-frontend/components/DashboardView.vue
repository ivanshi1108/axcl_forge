<template>
  <div class="container">

    <div class="charts-grid">
      <div class="chart-card memory-card">
        <div class="memory-header">
          <h2>CMM 内存</h2>
          <span v-if="cmmMem.total_kb !== null" class="memory-total"> {{ formatMB(cmmMem.total_kb) }} MB</span>
        </div>
        <div v-if="cmmMem.total_kb !== null" class="usage-bar mem-usage" aria-label="CMM memory usage bar">
          <span class="usage-percent">{{ cmmUsage.percent.toFixed(1) }}%</span>
          <div class="usage-fill memory-fill" :style="memoryUsedStyle(cmmUsage.percent)">
          </div>
          <div class="usage-rest" :style="{ width: (100 - cmmUsage.percent) + '%' }"></div>
        </div>
        <p v-else class="chart-loading">正在获取 CMM 内存信息...</p>
        <div v-if="cmmMem.total_kb !== null" class="memory-meta">
          <span>已用 {{ cmmUsage.usedLabel }}</span>
          <span>剩余 {{ cmmUsage.freeLabel }}</span>
        </div>
      </div>

      <div class="chart-card memory-card">
        <div class="memory-header">
          <h2>OS 内存</h2>
          <span v-if="osMem.total_kb !== null" class="memory-total"> {{ formatMB(osMem.total_kb) }} MB</span>
        </div>
        <div v-if="osMem.total_kb !== null" class="usage-bar mem-usage" aria-label="OS memory usage bar">
          <span class="usage-percent">{{ osUsage.percent.toFixed(1) }}%</span>
          <div class="usage-fill memory-fill" :style="memoryUsedStyle(osUsage.percent)">
          </div>
          <div class="usage-rest" :style="{ width: (100 - osUsage.percent) + '%' }"></div>
        </div>
        <p v-else class="chart-loading">正在获取 OS 内存信息...</p>
        <div v-if="osMem.total_kb !== null" class="memory-meta">
          <span>已用 {{ osUsage.usedLabel }}</span>
          <span>剩余 {{ osUsage.freeLabel }}</span>
        </div>
      </div>

      <div class="chart-card memory-card">
        <div class="memory-header">
          <h2>RAMDisk</h2>
          <span v-if="ramdisk.size_kb" class="memory-total"> {{ formatMB(ramdisk.size_kb) }} MB</span>
        </div>
        <div v-if="ramdisk.size_kb" class="usage-bar mem-usage" aria-label="RAMDisk usage bar">
          <span class="usage-percent">{{ ramdisk.percentNum.toFixed(1) }}%</span>
          <div class="usage-fill memory-fill" :style="memoryUsedStyle(ramdisk.percentNum)">
          </div>
          <div class="usage-rest" :style="{ width: (100 - ramdisk.percentNum) + '%' }"></div>
        </div>
        <p v-else class="chart-loading">正在获取 RAMDisk 信息...</p>
        <div v-if="ramdisk.size_kb" class="memory-meta">
          <span>已用 {{ formatMB(ramdisk.used_kb) }} MB</span>
          <span>剩余 {{ formatMB(ramdisk.avail_kb) }} MB</span>
        </div>
      </div>
    </div>

    <div class="util-row">
      <div class="chart-card cpu-card">
        <div class="card-header">
          <h2>CPU 使用率</h2>
        </div>
        <div v-if="cpuData.history.length" ref="cpuChartRef" class="chart"></div>
        <p v-else class="chart-loading">正在加载 CPU 使用率...</p>
      </div>

      <div class="util-side">
        <div class="chart-card npu-card">
          <div class="card-header">
            <h2>NPU 使用率</h2>
          </div>
          <div v-if="npuPercent !== null" class="usage-bar mem-usage" aria-label="NPU usage bar">
            <span class="usage-percent">{{ npuPercent.toFixed(1) }}%</span>
            <div class="usage-fill" :style="npuFillStyle">
            </div>
            <div class="usage-rest" :style="{ width: (100 - npuPercent) + '%' }"></div>
          </div>
          <p v-else class="chart-loading">正在获取 NPU 使用率...</p>
        </div>

        <div class="chart-card temp-card">
          <div class="card-header">
            <h2>温度</h2>
          </div>
          <div v-if="tempDisplay.percent !== null" class="usage-bar temp-bar mem-usage" aria-label="Temperature bar">
            <span class="usage-percent">{{ temperature.celsius.toFixed(1) }} ℃</span>
            <div class="usage-fill temp-fill" :style="tempFillStyle">
            </div>
            <div class="usage-rest" :style="{ width: (100 - tempDisplay.percent) + '%' }"></div>
          </div>
          <p v-else class="chart-loading">正在获取温度...</p>
        </div>
      </div>
    </div>

    <div class="refresh-config">
      <label>自动刷新间隔: </label>
      <select v-model="selectedInterval" @change="updateRefreshInterval">
        <option value="0">不刷新</option>
        <option value="1000">1秒</option>
        <option value="5000">5秒</option>
        <option value="10000">10秒</option>
        <option value="30000">30秒</option>
        <option value="60000">60秒</option>
      </select>
    </div>

    <div class="stats-toggle">
      <button class="toggle-btn" type="button" @click="showStats = !showStats">
        <span>API 统计</span>
        <span class="action">{{ showStats ? '收起' : '展开' }}</span>
      </button>
    </div>

    <div v-show="showStats" class="table-wrapper">
      <table class="stats-table">
        <thead>
          <tr>
            <th>API 路径</th>
            <th>调用次数</th>
            <th>最后调用时间</th>
            <th>最后调用IP</th>
            <th>最近一次耗时 (ms)</th>
            <th>平均耗时 (ms)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(stat, path) in stats" :key="path">
            <td>{{ path }}</td>
            <td>{{ stat.count }}</td>
            <td>{{ formatTime(stat.last_time) }}</td>
            <td>{{ stat.last_ip }}</td>
            <td>{{ stat.last_duration_ms ? stat.last_duration_ms.toFixed(2) : '-' }}</td>
            <td>{{ stat.avg_duration_ms ? stat.avg_duration_ms.toFixed(2) : '-' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="Object.keys(stats).length === 0" class="empty">暂无统计数据</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, onActivated, watch, nextTick } from 'vue'
import axios from 'axios'
import * as echarts from 'echarts'
import { getApiBase } from '../apiBase'

const stats = ref({})
const showStats = ref(false)
const cmmMem = ref({ total_kb: null, used_kb: null })
const osMem = ref({ total_kb: null, available_kb: null })
const cpuData = ref({ usage_percent: 0, timestamp: null, history: [] })
const npuUsage = ref({ percent: null, timestamp: null, raw: '' })
const ramdisk = ref({ size_kb: null, used_kb: null, avail_kb: null, percentNum: 0 })
const temperature = ref({ celsius: null, raw: '', timestamp: null })
const cpuChartRef = ref(null)
let cpuChart = null
let refreshInterval = null
const API_BASE = getApiBase()

const formatMB = (kb) => {
  if (kb === null || kb === undefined) return '-'
  return Number((kb / 1024).toFixed(1))
}
const normalizePercent = (val) => {
  if (val === null || val === undefined) return 0
  const str = String(val).replace('%', '')
  const num = Number(str)
  if (Number.isNaN(num)) return 0
  return Math.max(0, Math.min(100, num))
}
const calcUsage = (totalKb = 0, usedKb = 0) => {
  const safeTotal = Math.max(totalKb, 0)
  const safeUsed = Math.min(Math.max(usedKb, 0), safeTotal)
  const free = Math.max(safeTotal - safeUsed, 0)
  const percent = safeTotal > 0 ? (safeUsed / safeTotal) * 100 : 0
  return {
    used: safeUsed,
    free,
    percent,
    usedLabel: `${formatMB(safeUsed)} MB`,
    freeLabel: `${formatMB(free)} MB`
  }
}

const cmmUsage = computed(() => calcUsage(cmmMem.value.total_kb || 0, cmmMem.value.used_kb || 0))
const osUsage = computed(() => {
  const total = osMem.value.total_kb || 0
  const available = osMem.value.available_kb || 0
  const used = Math.max(total - available, 0)
  return calcUsage(total, used)
})

const memoryUsedStyle = (percent) => {
  const safe = Math.max(0, Math.min(100, percent || 0))
  return {
    width: `${safe}%`,
    background: getHeatGradient(safe),
    color: safe > 65 ? '#0b0f1d' : '#e5e7eb'
  }
}
const isTiny = (percent) => (percent || 0) < 12
const npuPercent = computed(() => {
  const p = npuUsage.value?.percent
  if (p === null || p === undefined) return null
  const num = Number(p)
  if (Number.isNaN(num)) return null
  return Math.min(100, Math.max(0, num))
})

const npuFillStyle = computed(() => {
  const percent = npuPercent.value ?? 0
  const palette = getHeatGradient(percent)
  return {
    width: `${percent}%`,
    background: palette,
    color: percent > 65 ? '#0b0f1d' : '#0b0f1d'
  }
})
const tempDisplay = computed(() => {
  const c = temperature.value?.celsius
  if (c === null || c === undefined) return { label: '-- ℃', percent: null }
  const num = Number(c)
  if (Number.isNaN(num)) return { label: '-- ℃', percent: null }
  const clamped = Math.min(110, Math.max(40, num))
  const percent = ((clamped - 40) / 70) * 100
  return { label: `${num.toFixed(1)} ℃`, percent }
})

const tempFillStyle = computed(() => {
  const percent = tempDisplay.value.percent ?? 0
  const celsius = temperature.value?.celsius ?? 0
  const palette = getHeatGradient(percent, celsius)
  return {
    width: `${percent}%`,
    background: palette,
    color: percent > 65 ? '#0b0f1d' : '#0b0f1d'
  }
})

const getHeatGradient = (percent, valueHint) => {
  const v = valueHint !== undefined && valueHint !== null ? Number(valueHint) : percent
  const p = Number.isNaN(v) ? percent : v
  const safe = Math.max(0, Math.min(100, p))

  let start = '#22d3ee'
  let end = '#22c55e'
  if (safe >= 70) {
    start = '#f59e0b'
    end = '#ef4444'
  } else if (safe >= 40) {
    start = '#22c55e'
    end = '#f59e0b'
  }
  return `linear-gradient(90deg, ${start} 0%, ${end} 100%)`
}

const statsCount = computed(() => Object.keys(stats.value || {}).length)

// Configurable refresh interval, default 10 seconds
const refreshIntervalMs = ref(10000)
const selectedInterval = ref('10000')

const updateRefreshInterval = () => {
  const ms = parseInt(selectedInterval.value)
  refreshIntervalMs.value = ms
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
  if (ms > 0) {
    refreshInterval = setInterval(fetchAllData, ms)
  }
}

const fetchStats = async () => {
  try {
    const res = await axios.get(`${API_BASE}/stats`)
    stats.value = res.data
  } catch (e) {
    stats.value = {}
  }
}


const fetchAllData = async () => {
  await Promise.all([
    fetchStats(),
    fetchSystemStatus()
  ])
  await nextTick()
  handleResize()
}

const fetchSystemStatus = async () => {
  try {
    const res = await axios.get(`${API_BASE}/system/status`)
    const data = res.data || {}
    // cmm_mem
    cmmMem.value = data.cmm_mem || { total_kb: null, used_kb: null }
    // os_mem
    osMem.value = data.os_mem || { total_kb: null, available_kb: null }
    // ramdisk
    const ram = data.ramdisk || {}
    ramdisk.value = {
      size_kb: ram.size_kb ?? null,
      used_kb: ram.used_kb ?? null,
      avail_kb: ram.avail_kb ?? null,
      percentNum: normalizePercent(ram.used_percent ?? ram.percent),
      mount: ram.mount || ram.filesystem || ''
    }
    // cpu
    cpuData.value = data.cpu || { usage_percent: 0, timestamp: null, history: [] }
    await nextTick()
    updateCpuChart()
    // npu
    npuUsage.value = data.npu || { percent: null, timestamp: null, raw: '' }
    // temperature
    temperature.value = data.temperature || { celsius: null, raw: '', timestamp: null }
  } catch (e) {
    cmmMem.value = { total_kb: null, used_kb: null }
    osMem.value = { total_kb: null, available_kb: null }
    ramdisk.value = { size_kb: null, used_kb: null, avail_kb: null, percentNum: 0, error: 'unavailable' }
    cpuData.value = { usage_percent: 0, timestamp: null, history: [] }
    npuUsage.value = { percent: null, timestamp: null, raw: '' }
    temperature.value = { celsius: null, raw: '', timestamp: null }
  }
}


// Remove separate system status API calls, all unified by fetchSystemStatus

const formatTime = (ts) => {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString()
}

const updateCpuChart = () => {
  if (!cpuChartRef.value || !cpuData.value.history || !cpuData.value.history.length) return
  if (!cpuChart) {
    cpuChart = echarts.init(cpuChartRef.value)
  }
  const categories = cpuData.value.history.map(item => new Date(item.timestamp * 1000).toLocaleTimeString())
  const values = cpuData.value.history.map(item => Number(item.usage_percent.toFixed(2)))
  cpuChart.setOption({
    tooltip: { trigger: 'axis', valueFormatter: value => `${value}%` },
    visualMap: {
      show: false,
      dimension: 1,
      pieces: [
        { min: 0, max: 20, color: '#22c55e' },
        { min: 20, max: 40, color: '#84cc16' },
        { min: 40, max: 60, color: '#eab308' },
        { min: 60, max: 80, color: '#f97316' },
        { min: 80, max: 100, color: '#ef4444' }
      ]
    },
    xAxis: {
      type: 'category',
      data: categories,
      boundaryGap: false,
      axisLabel: { color: '#e5e7eb' }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { formatter: '{value}%', color: '#e5e7eb' }
    },
    grid: { left: 50, right: 20, bottom: 40, top: 30 },
    series: [
      {
        data: values,
        type: 'line',
        smooth: true,
        areaStyle: {},
        showSymbol: false
      }
    ]
  })
  cpuChart.resize()
}

const handleResize = () => {
  cpuChart && cpuChart.resize()
}

watch(cpuData, updateCpuChart, { deep: true })

onMounted(() => {
  fetchAllData()
  updateRefreshInterval()
  requestAnimationFrame(handleResize)
  window.addEventListener('resize', handleResize)
})

onActivated(() => {
  fetchAllData()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  cpuChart && cpuChart.dispose()
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
})
</script>

<style scoped>
.container {
  max-width: 1000px;
  margin: 20px auto;
  background: linear-gradient(135deg, rgba(17, 24, 39, 0.9), rgba(10, 12, 26, 0.9));
  border: 1px solid rgba(59, 130, 246, 0.24);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.45), inset 0 0 0 1px rgba(16, 185, 129, 0.08);
  padding: 32px 24px 24px 24px;
  color: #e5e7eb;
  position: relative;
  overflow: hidden;
}
h1 {
  text-align: center;
  color: #e5e7eb;
  margin-bottom: 24px;
  font-size: 2.3rem;
  letter-spacing: 3px;
}
.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 18px;
  margin-bottom: 22px;
}
.chart-card {
  background: linear-gradient(180deg, rgba(22, 28, 45, 0.95), rgba(16, 21, 34, 0.95));
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 14px 34px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(59, 130, 246, 0.12);
  position: relative;
  overflow: hidden;
}
.memory-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chart-card::after {
  content: '';
  position: absolute;
  inset: -40% 10% auto auto;
  width: 160px;
  height: 160px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.25), transparent 60%);
  filter: blur(16px);
  pointer-events: none;
}
.chart-card::before {
  content: '';
  position: absolute;
  inset: auto auto -45% -5%;
  width: 180px;
  height: 180px;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.25), transparent 60%);
  filter: blur(18px);
  pointer-events: none;
}
.temp-bar {
  background: #fff4e6;
}
.temp-fill {
  background: linear-gradient(90deg, #2dd4bf 0%, #f59e0b 50%, #ef4444 100%);
}
.memory-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.memory-card .memory-total {
  position: static;
  margin-left: auto;
  padding: 4px 10px;
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.16);
  border: 1px solid rgba(59, 130, 246, 0.28);
  color: #e5e7eb;
  font-weight: 600;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3), inset 0 0 0 1px rgba(16, 185, 129, 0.08);
}
.memory-bar {
  position: relative;
  display: flex;
  border-radius: 16px;
  overflow: visible;
  background: rgba(15, 23, 42, 0.6);
  height: 42px;
  box-shadow: inset 0 1px 4px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(59, 130, 246, 0.12);
}
.memory-used,
.memory-free {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0b0f1d;
  font-weight: 600;
  font-size: 0.9rem;
  white-space: nowrap;
  transition: width 0.3s ease, box-shadow 0.3s ease;
  position: relative;
}
.memory-used[data-has-usage="true"] {
  min-width: 28px;
}
.memory-used {
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.28), inset 0 0 0 1px rgba(255, 255, 255, 0.08);
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.25);
}
.memory-free {
  background: linear-gradient(90deg, rgba(16, 185, 129, 0.6) 0%, rgba(14, 165, 233, 0.5) 90%);
  color: #cbd5e1;
}
.memory-used.tiny-usage span,
.memory-free.tiny-usage span {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  white-space: nowrap;
  pointer-events: none;
  font-size: 0.82rem;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.45);
}
.memory-used.tiny-usage span {
  left: 8px;
  color: #e5e7eb;
}
.memory-free.tiny-usage span {
  right: 8px;
  left: auto;
  color: #e5e7eb;
}
.ramdisk-bar .memory-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  font-weight: 600;
  font-size: 0.86rem;
  color: #e5e7eb;
  pointer-events: none;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.55);
}
.ramdisk-bar .memory-used > span,
.ramdisk-bar .memory-free > span {
  display: none;
}
.memory-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px 12px;
  align-items: center;
  font-size: 0.9rem;
  color: #cbd5e1;
}
.memory-meta span {
  display: inline-flex;
  align-items: center;
}
.cpu-card {
  flex: 1;
  min-width: 320px;
  display: flex;
  flex-direction: column;
}
.npu-card {
  margin: 0;
}
.temp-card {
  margin: 0;
  text-align: center;
}
.util-row {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 16px;
  margin-bottom: 24px;
  align-items: stretch;
}
.util-row > * {
  min-height: 0;
}
.util-side {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 16px;
  min-width: 280px;
  height: 100%;
}
.util-side > .chart-card {
  display: flex;
  flex-direction: column;
}
.chart-card h2 {
  text-align: center;
  margin-bottom: 12px;
  margin-top: -4px;
  color: #e5e7eb;
  letter-spacing: 0.5px;
  text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}
.usage-bar {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(59, 130, 246, 0.12);
  height: 36px;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.08);
  position: relative;
}
.usage-percent {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 1.2rem;
  font-weight: 700;
  color: #fff;
  padding: 4px 10px;
  border-radius: 8px;
  z-index: 10;
  text-shadow: 2px 2px 5px rgba(0,0,0,0.9);
}
.mem-usage {
  height: 50px;
  border-radius: 16px;
}
.usage-fill {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0b0f1d;
  font-weight: 700;
  white-space: nowrap;
  transition: width 0.3s ease;
}
.usage-rest {
  background: rgba(255,255,255,0.08);
  transition: width 0.3s ease;
}
.temp-value {
  font-size: 2.4rem;
  font-weight: 700;
  color: #f472b6;
  margin: 8px 0 4px;
}
.chart {
  width: 100%;
  height: 100%;
  min-height: 240px;
  flex: 1;
}
.chart-loading {
  text-align: center;
  color: #9ca3af;
  padding: 32px 0;
}
.stats-toggle {
  display: flex;
  justify-content: flex-start;
  margin: 12px 0;
}
.toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.14);
  border: 1px solid rgba(59, 130, 246, 0.35);
  color: #e5e7eb;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 10px 30px rgba(0,0,0,0.25), inset 0 0 0 1px rgba(255, 255, 255, 0.06);
  transition: transform 0.1s ease, box-shadow 0.2s ease, background 0.2s ease;
}
.toggle-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 30px rgba(0,0,0,0.32), inset 0 0 0 1px rgba(255, 255, 255, 0.08);
  background: rgba(59, 130, 246, 0.2);
}
.toggle-btn:active {
  transform: translateY(0);
}
.toggle-btn .badge {
  min-width: 28px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(16, 185, 129, 0.22);
  border: 1px solid rgba(16, 185, 129, 0.4);
  color: #bbf7d0;
  text-align: center;
  font-size: 0.9rem;
}
.toggle-btn .action {
  font-size: 0.9rem;
  opacity: 0.9;
}
.refresh-config {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 8px;
  margin-top: 20px;
  font-size: 0.9rem;
  color: #cbd5e1;
}
.refresh-config select {
  padding: 6px 10px;
  border: 1px solid #334155;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.9);
  color: #e5e7eb;
  box-shadow: 0 6px 18px rgba(0,0,0,0.25), inset 0 0 0 1px rgba(59, 130, 246, 0.12);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}
.refresh-config select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
}
.table-wrapper {
  overflow-x: auto;
}
.stats-table {
  width: 100%;
  border-collapse: collapse;
  background: rgba(17, 24, 39, 0.8);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.08);
}
.stats-table th, .stats-table td {
  padding: 14px 12px;
  text-align: center;
}
.stats-table th {
  background: rgba(59, 130, 246, 0.15);
  color: #e5e7eb;
  font-weight: 700;
  border-bottom: 1px solid rgba(59, 130, 246, 0.25);
}
.stats-table tr:nth-child(even) {
  background: rgba(255, 255, 255, 0.02);
}
.stats-table tr:hover {
  background: rgba(59, 130, 246, 0.12);
}
.empty {
  text-align: center;
  color: #9ca3af;
  margin-top: 24px;
}
@media (max-width: 768px) {
  .util-row {
    grid-template-columns: 1fr;
    gap: 16px;
  }
  .util-side {
    grid-template-rows: 1fr 1fr;
    gap: 16px;
  }
  .cpu-card {
    min-width: auto;
  }
}

</style>
