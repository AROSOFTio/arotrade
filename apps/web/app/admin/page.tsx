'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import axios from 'axios'

export default function AdminPage() {
  const router = useRouter()
  const [stats, setStats] = useState<any>(null)
  const [users, setUsers] = useState<any[]>([])
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'dashboard' | 'users' | 'logs' | 'settings'>('dashboard')

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      router.push('/login')
      return
    }

    fetchAdminData(token)
  }, [router])

  const fetchAdminData = async (token: string) => {
    try {
      const [statsRes, usersRes, logsRes] = await Promise.all([
        axios.get(`${process.env.NEXT_PUBLIC_API_URL}/admin/dashboard`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        axios.get(`${process.env.NEXT_PUBLIC_API_URL}/admin/users`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        axios.get(`${process.env.NEXT_PUBLIC_API_URL}/admin/audit-logs`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ])

      setStats(statsRes.data)
      setUsers(usersRes.data)
      setLogs(logsRes.data)
    } catch (err) {
      console.error('Failed to fetch admin data:', err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  }

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-red-400">🔐 Admin Panel</h1>
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
      </header>

      {/* Tabs */}
      <div className="border-b border-slate-800 sticky top-0 bg-slate-950/90 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex gap-8">
          {(['dashboard', 'users', 'logs', 'settings'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`py-4 px-2 border-b-2 font-medium transition-colors ${
                tab === t
                  ? 'border-blue-600 text-blue-400'
                  : 'border-transparent text-slate-400 hover:text-white'
              }`}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Dashboard Tab */}
        {tab === 'dashboard' && stats && (
          <div>
            <h2 className="text-2xl font-bold mb-8">Dashboard Overview</h2>
            <div className="grid md:grid-cols-4 gap-4">
              {[
                { label: 'Total Users', value: stats.total_users, icon: '👥' },
                { label: 'Active Users', value: stats.active_users, icon: '✅' },
                { label: 'Signals Generated', value: stats.total_signals, icon: '📊' },
                { label: 'Demo Trades', value: stats.demo_trades, icon: '📈' },
                { label: 'Live Trades', value: stats.live_trades, icon: '💰' },
                { label: 'Failed Trades', value: stats.failed_trades, icon: '❌' },
                { label: 'Risk Violations', value: stats.risk_violations, icon: '⚠️' },
                { label: 'API Errors', value: stats.api_errors, icon: '🔴' },
              ].map((stat, i) => (
                <div key={i} className="card">
                  <div className="text-3xl mb-2">{stat.icon}</div>
                  <p className="text-slate-400 text-sm">{stat.label}</p>
                  <p className="text-2xl font-bold mt-1">{stat.value}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Users Tab */}
        {tab === 'users' && (
          <div>
            <h2 className="text-2xl font-bold mb-8">Manage Users</h2>
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4">Email</th>
                    <th className="text-left py-3 px-4">Role</th>
                    <th className="text-left py-3 px-4">Status</th>
                    <th className="text-left py-3 px-4">Live Trading</th>
                    <th className="text-left py-3 px-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id} className="border-b border-slate-800 hover:bg-slate-900/50">
                      <td className="py-3 px-4">{user.email}</td>
                      <td className="py-3 px-4 capitalize">
                        <span
                          className={`px-2 py-1 rounded text-xs font-medium ${
                            user.role === 'admin'
                              ? 'bg-red-900/30 text-red-300'
                              : 'bg-blue-900/30 text-blue-300'
                          }`}
                        >
                          {user.role}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-1 rounded text-xs font-medium ${
                            user.is_active
                              ? 'bg-green-900/30 text-green-300'
                              : 'bg-gray-900/30 text-gray-300'
                          }`}
                        >
                          {user.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        {user.enable_live_trading ? '✅' : '❌'}
                      </td>
                      <td className="py-3 px-4">
                        <button className="text-blue-400 hover:text-blue-300">
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Audit Logs Tab */}
        {tab === 'logs' && (
          <div>
            <h2 className="text-2xl font-bold mb-8">Audit Logs</h2>
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4">Timestamp</th>
                    <th className="text-left py-3 px-4">User</th>
                    <th className="text-left py-3 px-4">Action</th>
                    <th className="text-left py-3 px-4">Resource</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id} className="border-b border-slate-800 hover:bg-slate-900/50">
                      <td className="py-3 px-4 text-slate-400 text-xs">
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                      <td className="py-3 px-4">{log.user_id}</td>
                      <td className="py-3 px-4 font-mono">{log.action}</td>
                      <td className="py-3 px-4 text-slate-400">{log.resource}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Settings Tab */}
        {tab === 'settings' && (
          <div>
            <h2 className="text-2xl font-bold mb-8">Global Settings</h2>
            <div className="card max-w-2xl">
              <div className="space-y-6">
                <div className="border-b border-slate-700 pb-6">
                  <label className="block font-medium mb-2">Enable Live Trading Globally</label>
                  <p className="text-slate-400 text-sm mb-4">
                    When disabled, no users can execute live trades regardless of individual settings.
                  </p>
                  <button className="btn-primary">
                    Currently: DISABLED
                  </button>
                </div>

                <div className="border-b border-slate-700 pb-6">
                  <label className="block font-medium mb-2">Default Risk Per Trade (%)</label>
                  <input type="number" defaultValue={1} className="input-base w-32" />
                </div>

                <div className="border-b border-slate-700 pb-6">
                  <label className="block font-medium mb-2">Max Daily Loss (%)</label>
                  <input type="number" defaultValue={3} className="input-base w-32" />
                </div>

                <button className="btn-primary">Save Settings</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
