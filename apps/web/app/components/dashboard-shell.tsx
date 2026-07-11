'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Activity,
  Bell,
  BookOpen,
  Bot,
  Calculator,
  CandlestickChart,
  Landmark,
  LayoutDashboard,
  LineChart,
  LogOut,
  Menu,
  Network,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
  type LucideIcon,
} from 'lucide-react'

import { apiRequest } from './api'
import { ThemeToggle } from './theme-toggle'

type User = {
  email: string
  full_name?: string | null
  role: string
  trading_mode: string
  enable_live_trading: boolean
}

type Notification = {
  id: number
  title: string
  body?: string | null
  category: string
  link?: string | null
  is_read: boolean
  created_at: string
}

type NavigationItem = {
  href: string
  label: string
  icon: LucideIcon
}

const navigation: NavigationItem[] = [
  { href: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { href: '/dashboard/markets', label: 'Markets', icon: Activity },
  { href: '/dashboard/signals', label: 'Signals', icon: Sparkles },
  { href: '/dashboard/trades', label: 'Paper trades', icon: CandlestickChart },
  { href: '/dashboard/strategy-builder', label: 'Strategies', icon: Network },
  { href: '/dashboard/backtesting', label: 'Backtesting', icon: LineChart },
  { href: '/dashboard/ai-analysis', label: 'AI analysis', icon: Bot },
  { href: '/dashboard/journal', label: 'Journal', icon: BookOpen },
  { href: '/dashboard/calculator', label: 'Position size', icon: Calculator },
  { href: '/dashboard/risk', label: 'Risk controls', icon: ShieldCheck },
  { href: '/dashboard/broker-accounts', label: 'Broker accounts', icon: Landmark },
  { href: '/dashboard/settings', label: 'Settings', icon: Settings2 },
]

function navigationIsActive(pathname: string, href: string) {
  return href === '/dashboard' ? pathname === href : pathname.startsWith(href)
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [isBellOpen, setIsBellOpen] = useState(false)

  const refreshNotifications = () => {
    apiRequest<Notification[]>('/notifications?limit=15').then(setNotifications).catch(() => undefined)
    apiRequest<{ unread: number }>('/notifications/unread-count').then((r) => setUnreadCount(r.unread)).catch(() => undefined)
  }

  useEffect(() => {
    refreshNotifications()
    const interval = window.setInterval(refreshNotifications, 60000)
    return () => window.clearInterval(interval)
  }, [])

  const markAllRead = async () => {
    try {
      await apiRequest('/notifications/read-all', { method: 'POST' })
      setUnreadCount(0)
      setNotifications((current) => current.map((n) => ({ ...n, is_read: true })))
    } catch {
      // non-fatal
    }
  }

  useEffect(() => {
    if (!window.localStorage.getItem('access_token')) {
      router.replace('/login')
      return
    }

    apiRequest<User>('/auth/me')
      .then(setUser)
      .catch(() => {
        window.localStorage.removeItem('access_token')
        window.localStorage.removeItem('refresh_token')
        router.replace('/login')
      })
      .finally(() => setIsLoading(false))
  }, [router])

  const activePage = useMemo(
    () => navigation.find((item) => navigationIsActive(pathname, item.href))?.label || 'Workspace',
    [pathname],
  )

  const initials = (user?.full_name || user?.email || 'AT')
    .split(/\s|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
  const isLiveMode = user?.enable_live_trading && user.trading_mode?.toLowerCase() === 'live'
  const modeBadgeClass = isLiveMode
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-blue-200 bg-blue-50 text-[#1d4ed8]'
  const executionBadgeClass = isLiveMode
    ? 'bg-emerald-50 text-emerald-700'
    : 'bg-blue-50 text-[#1d4ed8]'

  const signOut = async () => {
    try {
      await apiRequest('/auth/logout', { method: 'POST' })
    } finally {
      window.localStorage.removeItem('access_token')
      window.localStorage.removeItem('refresh_token')
      router.replace('/login')
    }
  }

  const sidebar = (
    <div className="flex h-full flex-col bg-white">
      <div className="flex h-[72px] items-center justify-between border-b border-slate-200 px-5">
        <Link href="/dashboard" className="flex items-center gap-3" onClick={() => setIsMobileNavOpen(false)}>
          <img src="/logo.png" alt="AroTrader logo" className="h-9 w-9" />
          <span>
            <span className="block text-sm font-bold text-slate-950">AroTrader</span>
            <span className="block text-[11px] font-medium text-slate-500">by AROFi</span>
          </span>
        </Link>
        <button type="button" className="icon-button lg:hidden" onClick={() => setIsMobileNavOpen(false)} title="Close navigation">
          <X size={18} aria-hidden="true" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-5" aria-label="Workspace navigation">
        <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">Workspace</p>
        <div className="space-y-1">
          {navigation.map((item) => {
            const Icon = item.icon
            const active = navigationIsActive(pathname, item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors ${
                  active ? 'bg-blue-50 text-[#1d4ed8]' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-950'
                }`}
              >
                <Icon size={18} strokeWidth={active ? 2.4 : 1.9} aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            )
          })}
        </div>
      </nav>

      <div className="border-t border-slate-200 p-3">
        <div className={`mb-3 flex items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold ${executionBadgeClass}`}>
          <ShieldCheck size={16} aria-hidden="true" />
          {isLiveMode ? 'Live execution enabled' : 'Paper execution only'}
        </div>
        <button type="button" onClick={signOut} className="flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-950">
          <LogOut size={18} aria-hidden="true" />
          Sign out
        </button>
      </div>
    </div>
  )

  if (isLoading) {
    return <div className="flex min-h-screen items-center justify-center bg-[#f6f7f9] text-sm font-medium text-slate-500">Loading workspace…</div>
  }

  return (
    <div className="min-h-screen bg-[#f6f7f9]">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-slate-200 lg:block">{sidebar}</aside>

      {isMobileNavOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button type="button" className="absolute inset-0 bg-slate-950/25" onClick={() => setIsMobileNavOpen(false)} aria-label="Close navigation overlay" />
          <aside className="relative h-full w-[min(18rem,88vw)] shadow-xl">{sidebar}</aside>
        </div>
      )}

      <div className="min-h-screen lg:pl-64">
        <header className="sticky top-0 z-30 flex h-[72px] items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" className="icon-button lg:hidden" onClick={() => setIsMobileNavOpen(true)} title="Open navigation">
              <Menu size={19} aria-hidden="true" />
            </button>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">{activePage}</p>
              <p className="hidden text-xs text-slate-500 sm:block">AroTrader workspace</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <span className={`hidden rounded-md border px-2.5 py-1 text-xs font-semibold sm:inline-flex ${modeBadgeClass}`}>{isLiveMode ? 'Live mode' : 'Demo mode'}</span>
            <ThemeToggle />
            <div className="relative">
              <button
                type="button"
                className="icon-button relative"
                title="Notifications"
                aria-label={unreadCount > 0 ? `Notifications (${unreadCount} unread)` : 'Notifications'}
                onClick={() => { setIsBellOpen((open) => !open); if (!isBellOpen) refreshNotifications() }}
              >
                <Bell size={18} aria-hidden="true" />
                {unreadCount > 0 && (
                  <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
              {isBellOpen && (
                <>
                  <button type="button" className="fixed inset-0 z-40 cursor-default" onClick={() => setIsBellOpen(false)} aria-label="Close notifications" tabIndex={-1} />
                  <div className="absolute right-0 z-50 mt-2 w-[min(22rem,90vw)] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl">
                    <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                      <h3 className="text-sm font-semibold text-slate-900">Notifications</h3>
                      {unreadCount > 0 && (
                        <button type="button" onClick={() => void markAllRead()} className="text-xs font-semibold text-[#2563eb] hover:text-[#1d4ed8]">Mark all read</button>
                      )}
                    </div>
                    <div className="max-h-96 overflow-y-auto">
                      {notifications.length === 0 ? (
                        <p className="px-4 py-8 text-center text-sm text-slate-500">No notifications yet.</p>
                      ) : (
                        notifications.map((notification) => (
                          <Link
                            key={notification.id}
                            href={notification.link || '/dashboard'}
                            onClick={() => setIsBellOpen(false)}
                            className={`block border-b border-slate-50 px-4 py-3 transition-colors hover:bg-slate-50 ${notification.is_read ? '' : 'bg-blue-50/50'}`}
                          >
                            <p className="text-sm font-semibold text-slate-900">{notification.title}</p>
                            {notification.body && <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-slate-500">{notification.body}</p>}
                          </Link>
                        ))
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
            <div className="flex items-center gap-2 border-l border-slate-200 pl-2 sm:pl-3">
              <span className="hidden max-w-40 truncate text-right text-sm font-medium text-slate-700 sm:block">{user?.full_name || user?.email}</span>
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white" title={user?.email}>{initials}</span>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8">{children}</main>

        <footer className="border-t border-slate-200 bg-white px-4 py-4 text-xs text-slate-500 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1600px] flex-col justify-between gap-1 sm:flex-row sm:items-center">
            <span>© {new Date().getFullYear()} AROFi. {isLiveMode ? 'AroTrader live execution is enabled.' : 'AroTrader is operating in paper mode.'}</span>
            <span>{isLiveMode ? 'Risk controls still apply to every live order.' : 'Live execution unlocks when a broker adapter is connected.'}</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
