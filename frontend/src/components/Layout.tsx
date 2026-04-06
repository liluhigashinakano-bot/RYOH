import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import BottomNav from './BottomNav'

export default function Layout() {
  return (
    <div className="flex min-h-screen" style={{ backgroundColor: '#0a0a0f' }}>
      <div className="hidden md:block">
        <Sidebar />
      </div>
      <main className="flex-1 md:ml-60 pb-20 md:pb-0 min-h-screen overflow-hidden">
        <div className="h-full p-4 md:p-6">
          <Outlet />
        </div>
      </main>
      <div className="md:hidden fixed bottom-0 left-0 right-0 z-50">
        <BottomNav />
      </div>
    </div>
  )
}
