import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiClient.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const res = await axios.post('/api/auth/refresh', { refresh_token: refresh })
          localStorage.setItem('access_token', res.data.access_token)
          localStorage.setItem('refresh_token', res.data.refresh_token)
          original.headers.Authorization = `Bearer ${res.data.access_token}`
          return apiClient(original)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          // Zustand persistのisLoggedInもクリア（ループ防止）
          const stored = localStorage.getItem('trust-auth')
          if (stored) {
            try {
              const parsed = JSON.parse(stored)
              parsed.state.isLoggedIn = false
              parsed.state.user = null
              parsed.state.stores = []
              localStorage.setItem('trust-auth', JSON.stringify(parsed))
            } catch {}
          }
          window.location.href = '/login'
        }
      } else {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        const stored = localStorage.getItem('trust-auth')
        if (stored) {
          try {
            const parsed = JSON.parse(stored)
            parsed.state.isLoggedIn = false
            parsed.state.user = null
            parsed.state.stores = []
            localStorage.setItem('trust-auth', JSON.stringify(parsed))
          } catch {}
        }
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
