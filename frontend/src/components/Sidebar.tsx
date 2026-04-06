import { NavLink } from 'react-router-dom'
import { LayoutDashboard, ShoppingCart, Users, Star, Settings, LogOut } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'ダッシュボード', exact: true },
  { to: '/pos', icon: ShoppingCart, label: 'POS・伝票' },
  { to: '/customers', icon: Users, label: '顧客管理' },
  { to: '/casts', icon: Star, label: '従業員管理' },
  { to: '/admin', icon: Settings, label: '管理者設定' },
]

export default function Sidebar() {
  const { user, logout } = useAuthStore()

  return (
    <aside className="fixed top-0 left-0 h-screen w-60 bg-gray-900 border-r border-gray-700 flex flex-col z-40">
      <div className="px-6 py-5 border-b border-gray-700">
        <h1 className="text-xl font-bold text-white tracking-widest">RYOH</h1>
        <p className="text-xs text-gray-500 mt-0.5">業務管理システム</p>
      </div>

      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label, exact }) => (
          <NavLink
            key={to}
            to={to}
            end={exact}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                isActive ? 'bg-pink-700 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`
            }
          >
            <Icon className="w-5 h-5 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-4 border-t border-gray-700">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 rounded-full bg-pink-700 flex items-center justify-center text-sm font-bold">
            {user?.name?.charAt(0)}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-white truncate">{user?.name}</p>
            <p className="text-xs text-gray-500">{user?.role}</p>
          </div>
        </div>
        <button onClick={logout} className="flex items-center gap-2 text-gray-500 hover:text-white text-sm transition-colors w-full">
          <LogOut className="w-4 h-4" />
          ログアウト
        </button>
      </div>
    </aside>
  )
}
