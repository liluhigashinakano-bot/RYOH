import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import apiClient from '../api/client'

interface User {
  id: number
  email: string
  name: string
  role: string
  store_id: number | null
}

interface Store {
  id: number
  name: string
  code: string
  set_price: number
  extension_price: number
  is_active: boolean
}

interface AuthState {
  user: User | null
  stores: Store[]
  isLoggedIn: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  fetchMe: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      stores: [],
      isLoggedIn: false,
      isLoading: false,

      login: async (email, password) => {
        set({ isLoading: true })
        try {
          const { data: tokens } = await apiClient.post('/api/auth/login', { email, password })
          localStorage.setItem('access_token', tokens.access_token)
          localStorage.setItem('refresh_token', tokens.refresh_token)

          const [{ data: user }, { data: stores }] = await Promise.all([
            apiClient.get('/api/auth/me'),
            apiClient.get('/api/stores'),
          ])

          set({ user, stores, isLoggedIn: true, isLoading: false })
        } catch (e) {
          set({ isLoading: false })
          throw e
        }
      },

      logout: () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({ user: null, stores: [], isLoggedIn: false })
      },

      fetchMe: async () => {
        const token = localStorage.getItem('access_token')
        if (!token) {
          // トークンなしでisLoggedInが残っていたらクリア（ループ防止）
          if (get().isLoggedIn) get().logout()
          return
        }
        try {
          const [{ data: user }, { data: stores }] = await Promise.all([
            apiClient.get('/api/auth/me'),
            apiClient.get('/api/stores'),
          ])
          set({ user, stores, isLoggedIn: true })
        } catch (e: any) {
          // 401のみログアウト。ネットワークエラー等では状態を保持
          if (e?.response?.status === 401) {
            get().logout()
          }
        }
      },
    }),
    {
      name: 'trust-auth',
      partialize: (s) => ({ user: s.user, stores: s.stores, isLoggedIn: s.isLoggedIn }),
    }
  )
)
