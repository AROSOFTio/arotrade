'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
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

type User = {
  email: string
  full_name?: string | null
  role: string
  trading_mode: string
  enable_live_trading: boolean
}

type NavigationItem = {
  href: string
  label: string
  icon: LucideIcon
}

const navigation: NavigationItem[] = [
  { href: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { href: '/dashboard/signals', label: 'Signals', icon: Sparkles },
  { href: '/dashboard/trades', label: 'Paper trades', icon: CandlestickChart },
  { href: '/dashboard/strategy-builder', label: 'Strategies', icon: Network },
  { href: '/dashboard/backtesting', label: 'Backtesting', icon: LineChart },
  { href: '/dashboard/ai-analysis', label: 'AI analysis', icon: Bot },
  { href: '/dashboard/journal', label: 'Journal', icon: BookOpen },
  { href: '/dashboard/calculator', label: 'Position size', icon: Calculator },
  { href: '/dashboard/risk', label: 'Risk controls', icon: ShieldCheck },
  { href: '/dashboard/broker-accounts', label: 'Demo accounts', icon: Landmark },
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
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#2563eb] text-sm font-black text-white">AT</span>
          <span>
            <span className="block text-sm font-bold text-slate-950">AroTrade</span>
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
        <div className="mb-3 flex items-center gap-2 rounded-md bg-blue-50 px-3 py-2 text-xs font-semibold text-[#1d4ed8]">
          <ShieldCheck size={16} aria-hidden="true" />
          Paper execution only
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
              <p className="hidden text-xs text-slate-500 sm:block">AroTrade workspace</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <span className="hidden rounded-md border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-[#1d4ed8] sm:inline-flex">Demo mode</span>
            <button type="button" className="icon-button" title="Notifications" aria-label="Notifications">
              <Bell size={18} aria-hidden="true" />
            </button>
            <div className="flex items-center gap-2 border-l border-slate-200 pl-2 sm:pl-3">
              <span className="hidden max-w-40 truncate text-right text-sm font-medium text-slate-700 sm:block">{user?.full_name || user?.email}</span>
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white" title={user?.email}>{initials}</span>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8">{children}</main>

        <footer className="border-t border-slate-200 bg-white px-4 py-4 text-xs text-slate-500 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1600px] flex-col justify-between gap-1 sm:flex-row sm:items-center">
            <span>© {new Date().getFullYear()} AROFi. AroTrade is operating in paper mode.</span>
            <span>Live execution unlocks when a broker adapter is connected.</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
