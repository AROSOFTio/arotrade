'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

export default function DashboardPage() {
  const router = useRouter()
  const [user, setUser] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      router.push('/login')
      return
    }

    // TODO: Fetch user data from API
    setUser({ email: 'user@example.com', role: 'trader' })
    setLoading(false)
  }, [router])

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  }

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800 sticky top-0 bg-slate-950/80 backdrop-blur-sm z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-blue-400">AroTrade AI</h1>
          <div className="flex items-center gap-4">
            <span className="text-slate-400">{user?.email}</span>
            <button
              onClick={() => {
                localStorage.removeItem('access_token')
                router.push('/login')
              }}
              className="btn-secondary text-sm"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Grid */}
        <div className="grid md:grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Demo Trades', value: '0', color: 'blue' },
            { label: 'Win Rate', value: '0%', color: 'green' },
            { label: 'Active Signals', value: '0', color: 'yellow' },
            { label: 'Account Balance', value: '$10,000', color: 'purple' },
          ].map((stat, i) => (
            <div key={i} className="card border-l-4 border-blue-600">
              <p className="text-slate-400 text-sm">{stat.label}</p>
              <p className="text-3xl font-bold mt-2">{stat.value}</p>
            </div>
          ))}
        </div>

        {/* Main Navigation */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[
            {
              icon: '🤖',
              title: 'AI Analysis',
              description: 'Analyze charts with Gemini AI',
              href: '/dashboard/ai-analysis',
            },
            {
              icon: '📊',
              title: 'Trading Signals',
              description: 'View and manage signals',
              href: '/dashboard/signals',
            },
            {
              icon: '🛠️',
              title: 'Strategy Builder',
              description: 'Create custom strategies',
              href: '/dashboard/strategy-builder',
            },
            {
              icon: '📈',
              title: 'Backtesting',
              description: 'Test strategies',
              href: '/dashboard/backtesting',
            },
            {
              icon: '📝',
              title: 'Trading Journal',
              description: 'Track trades and lessons',
              href: '/dashboard/journal',
            },
            {
              icon: '🛡️',
              title: 'Risk Settings',
              description: 'Configure risk parameters',
              href: '/dashboard/risk',
            },
            {
              icon: '💼',
              title: 'Broker Accounts',
              description: 'Manage accounts',
              href: '/dashboard/broker-accounts',
            },
            {
              icon: '💰',
              title: 'Trades',
              description: 'View execution logs',
              href: '/dashboard/trades',
            },
            {
              icon: '⚙️',
              title: 'Settings',
              description: 'User preferences',
              href: '/dashboard/settings',
            },
          ].map((item, i) => (
            <Link
              key={i}
              href={item.href}
              className="card hover:border-blue-600 hover:bg-slate-800/50 transition-all group cursor-pointer"
            >
              <div className="text-4xl mb-4 group-hover:scale-110 transition-transform">{item.icon}</div>
              <h3 className="font-bold text-lg mb-1">{item.title}</h3>
              <p className="text-slate-400 text-sm">{item.description}</p>
            </Link>
          ))}
        </div>

        {/* Warning Banner */}
        <div className="mt-12 p-6 bg-yellow-900/20 border border-yellow-900/50 rounded-lg">
          <p className="text-yellow-300 font-semibold mb-2">⚠️ Demo Mode Active</p>
          <p className="text-yellow-200/80">
            You are currently in demo trading mode. All trades are simulated and no real money is at risk. Switch to live mode in settings only after thorough testing.
          </p>
        </div>
      </div>
    </div>
  )
}
