// Centralized API base helpers to avoid hardcoding localhost in builds.
export const getApiBase = () => {
  const envBase = import.meta.env?.VITE_API_BASE
  if (envBase) return envBase.replace(/\/$/, '')

  const { protocol, hostname, port } = window.location
  const defaultPort = import.meta.env?.DEV ? '8018' : '8016'
  const apiPort = import.meta.env?.VITE_API_PORT || defaultPort
  const usePort = port && port !== '80' && port !== '443' ? apiPort : apiPort
  return `${protocol}//${hostname}${usePort ? `:${usePort}` : ''}`
}

export const getWsBase = () => {
  const envWs = import.meta.env?.VITE_WS_BASE
  if (envWs) return envWs.replace(/\/$/, '')

  const { protocol, hostname, port } = window.location
  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:'
  const defaultPort = import.meta.env?.DEV ? '8018' : '8016'
  const wsPort = import.meta.env?.VITE_WS_PORT || defaultPort
  const usePort = port && port !== '80' && port !== '443' ? wsPort : wsPort
  return `${wsProtocol}//${hostname}${usePort ? `:${usePort}` : ''}`
}
