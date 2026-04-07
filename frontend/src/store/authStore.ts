import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import apiClient from '../api/client'

export type PermPage = 'realtime' | 'pos' | 'customers' | 'employees' | 'accounts' | 'menus'
export type PermType = 'view' | 'edit'

export interface Permissions {
  realtime?: { view?: boolean }
  pos?: { view?: boolean; edit?: boolean }
  customers?: { view?: boolean; edit?: boolean }
  employees?: { view?: boolean; edit?: boolean }
  accounts?: { view?: boolean; edit?: boolean }
  menus?: { view?: boolean; edit?: boolean }
}

interface User {
  id: number
  email: string
  name: string
  role: string
  store_id: number | null
  permissions: Permissions | null
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
  hasPermission: (page: PermPage, type: PermType) => boolean
  isAdministrator: () => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      stores: [],
      isLoggedIn: false,
      isLoading: false,

      isAdministrator: () => {
        const role = get().user?.role
        return role === 'administrator' || role === 'superadmin'
      },

      hasPermission: (page: PermPage, type: PermType) => {
        const user = get().user
        if (!user) return false
        if (user.role === 'administrator' || user.role === 'superadmin') return true
        const perms = user.permissions
        if (!perms) return false
        return !!(perms[page] as any)?.[type]
      },

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
