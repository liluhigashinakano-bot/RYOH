import { NavLink } from 'react-router-dom'
import { LayoutDashboard, ShoppingCart, Users, Star, UserCog, SlidersHorizontal } from 'lucide-react'

const items = [
  { to: '/', icon: LayoutDashboard, label: 'ホーム', exact: true },
  { to: '/pos', icon: ShoppingCart, label: 'POS' },
  { to: '/customers', icon: Users, label: '顧客' },
  { to: '/casts', icon: Star, label: '従業員' },
  { to: '/admin', icon: UserCog, label: 'アカウント' },
  { to: '/settings', icon: SlidersHorizontal, label: '管理設定' },
]

export default function BottomNav() {
  return (
    <nav style={{ backgroundColor: '#111827', borderTop: '1px solid #374151' }} className="flex">
      {items.map(({ to, icon: Icon, label, exact }) => (
        <NavLink
          key={to}
          to={to}
          end={exact}
          className={({ isActive }) =>
            `flex-1 flex flex-col items-center gap-1 py-2 text-xs transition-colors ${
              isActive ? 'text-pink-400' : 'text-gray-500'
            }`
          }
        >
          <Icon className="w-5 h-5" />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}
