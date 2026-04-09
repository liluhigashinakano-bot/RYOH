import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './store/authStore'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import POS from './pages/pos/POS'
import CustomerList from './pages/customers/CustomerList'
import CustomerDetail from './pages/customers/CustomerDetail'
import CastList from './pages/casts/CastList'
import CastDetail from './pages/casts/CastDetail'
import AdminPanel from './pages/admin/AdminPanel'
import AdminSettings from './pages/admin/AdminSettings'
import MonthlyReport from './pages/reports/MonthlyReport'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
})

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: string }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false, error: '' }
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '20px', color: 'white', backgroundColor: '#0a0a0f', minHeight: '100vh' }}>
          <h1 style={{ color: '#f87171' }}>エラーが発生しました</h1>
          <pre style={{ color: '#9ca3af', fontSize: '12px', marginTop: '10px' }}>{this.state.error}</pre>
          <button
            onClick={() => { this.setState({ hasError: false }); window.location.reload() }}
            style={{ marginTop: '20px', padding: '10px 20px', backgroundColor: '#be185d', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer' }}
          >
            リロード
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn)
  if (!isLoggedIn) return <Navigate to="/login" replace />
  return <>{children}</>
}

function PermRoute({ page, children }: { page: import('./store/authStore').PermPage; children: React.ReactNode }) {
  const { hasPermission, isLoading } = useAuthStore()
  if (isLoading) return null
  if (!hasPermission(page, 'view')) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-400 text-sm">このページへのアクセス権限がありません</p>
      </div>
    )
  }
  return <>{children}</>
}

function AppRoutes() {
  const { isLoggedIn, fetchMe } = useAuthStore()

  useEffect(() => {
    fetchMe()
  }, [])

  return (
    <Routes>
      <Route path="/login" element={isLoggedIn ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<PermRoute page="realtime"><Dashboard /></PermRoute>} />
        <Route path="pos" element={<PermRoute page="pos"><POS /></PermRoute>} />
        <Route path="customers" element={<PermRoute page="customers"><CustomerList /></PermRoute>} />
        <Route path="customers/:id" element={<PermRoute page="customers"><CustomerDetail /></PermRoute>} />
        <Route path="casts" element={<PermRoute page="employees"><CastList /></PermRoute>} />
        <Route path="casts/:id" element={<PermRoute page="employees"><CastDetail /></PermRoute>} />
        <Route path="admin" element={<PermRoute page="accounts"><AdminPanel /></PermRoute>} />
        <Route path="settings" element={<PermRoute page="menus"><AdminSettings /></PermRoute>} />
        <Route path="reports/monthly" element={<PermRoute page="accounts"><MonthlyReport /></PermRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
