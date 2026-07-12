'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import axios from 'axios'

export default function AdminPage() {
  const router = useRouter()
  const [stats, setStats] = useState<any>(null)
  const [users, setUsers] = useState<any[]>([])
  const [logs, setLogs] = useState<any[]>([])
  const [liveControl, setLiveControl] = useState<any>(null)
  const [controlForm, setControlForm] = useState<any>(null)
  const [controlReason, setControlReason] = useState('')
  const [controlConfirmation, setControlConfirmation] = useState('')
  const [controlMessage, setControlMessage] = useState('')
  const [controlSaving, setControlSaving] = useState(false)
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
      const [statsRes, usersRes, logsRes, liveControlRes] = await Promise.all([
        axios.get(`${process.env.NEXT_PUBLIC_API_URL}/admin/dashboard`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        axios.get(`${process.env.NEXT_PUBLIC_API_URL}/admin/users`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        axios.get(`${process.env.NEXT_PUBLIC_API_URL}/admin/audit-logs`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        axios.get(`${process.env.NEXT_PUBLIC_API_URL}/admin/live-control`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ])

      setStats(statsRes.data)
      setUsers(usersRes.data)
      setLogs(logsRes.data)
      setLiveControl(liveControlRes.data)
      setControlForm(liveControlRes.data.control)
    } catch (err) {
      console.error('Failed to fetch admin data:', err)
    } finally {
      setLoading(false)
    }
  }

  const updateControl = (field: string, value: boolean) => {
    setControlForm((current: any) => ({ ...current, [field]: value }))
  }

  const saveLiveControl = async () => {
    const token = localStorage.getItem('access_token')
    if (!token || !controlForm) return
    setControlSaving(true)
    setControlMessage('')
    try {
      const response = await axios.patch(`${process.env.NEXT_PUBLIC_API_URL}/admin/live-control`, {
        live_trading_allowed: controlForm.live_trading_allowed,
        new_live_entries_allowed: controlForm.new_live_entries_allowed,
        broker_demo_trading_allowed: controlForm.broker_demo_trading_allowed,
        paper_trading_allowed: controlForm.paper_trading_allowed,
        live_position_management_allowed: controlForm.live_position_management_allowed,
        reason: controlReason,
        confirmation: controlConfirmation,
      }, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setLiveControl(response.data)
      setControlForm(response.data.control)
      setControlReason('')
      setControlConfirmation('')
      setControlMessage('Live trading controls saved.')
    } catch (err: any) {
      setControlMessage(err?.response?.data?.detail || 'Could not save live trading controls.')
    } finally {
      setControlSaving(false)
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
            <h2 className="text-2xl font-bold mb-8">Live Trading Control</h2>
            {controlMessage && <div className="mb-5 rounded-md border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-200">{controlMessage}</div>}
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
              <div className="card">
                <h3 className="text-lg font-semibold text-white">Platform status</h3>
                <div className="mt-5 space-y-4">
                  {[
                    ['live_trading_allowed', 'Global live permission'],
                    ['new_live_entries_allowed', 'New live entries allowed'],
                    ['broker_demo_trading_allowed', 'Broker-demo trading allowed'],
                    ['paper_trading_allowed', 'Paper trading allowed'],
                    ['live_position_management_allowed', 'Live position management allowed'],
                  ].map(([field, label]) => (
                    <label key={field} className="flex items-center justify-between gap-4 rounded-md border border-slate-700 px-4 py-3">
                      <span>
                        <span className="block text-sm font-semibold text-slate-100">{label}</span>
                        <span className="text-xs text-slate-400">{controlForm?.[field] ? 'Allowed' : 'Paused'}</span>
                      </span>
                      <input
                        type="checkbox"
                        checked={Boolean(controlForm?.[field])}
                        onChange={(event) => updateControl(field, event.target.checked)}
                        className="h-5 w-5 accent-blue-500"
                      />
                    </label>
                  ))}
                </div>

                <div className="mt-6 grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-slate-200">Reason</label>
                    <textarea className="input-base mt-2 min-h-24" value={controlReason} onChange={(event) => setControlReason(event.target.value)} placeholder="Why is this control changing?" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-200">Typed confirmation</label>
                    <input className="input-base mt-2" value={controlConfirmation} onChange={(event) => setControlConfirmation(event.target.value)} placeholder="CONFIRM" />
                    <p className="mt-2 text-xs text-slate-400">Changing platform trading permissions requires CONFIRM.</p>
                  </div>
                </div>
                <button type="button" disabled={controlSaving || controlConfirmation.trim().toUpperCase() !== 'CONFIRM' || controlReason.trim().length < 5} onClick={() => void saveLiveControl()} className="btn-primary mt-5">
                  {controlSaving ? 'Saving...' : 'Save live controls'}
                </button>
              </div>

              <div className="space-y-6">
                <div className="card">
                  <h3 className="text-sm font-semibold text-white">Account summary</h3>
                  <dl className="mt-4 space-y-3 text-sm">
                    {[
                      ['Connected live accounts', liveControl?.account_summary?.connected_live_accounts],
                      ['Connected demo accounts', liveControl?.account_summary?.connected_demo_accounts],
                      ['Open live positions', liveControl?.account_summary?.open_live_positions],
                      ['Pending live orders', liveControl?.account_summary?.pending_live_orders],
                      ['Unknown execution states', liveControl?.account_summary?.unknown_execution_states],
                      ['Reconciliation mismatches', liveControl?.account_summary?.reconciliation_mismatches],
                    ].map(([label, value]) => (
                      <div key={label} className="flex justify-between gap-4 border-b border-slate-800 pb-2">
                        <dt className="text-slate-400">{label}</dt>
                        <dd className="font-semibold text-slate-100">{value ?? 0}</dd>
                      </div>
                    ))}
                  </dl>
                </div>

                <div className="card">
                  <h3 className="text-sm font-semibold text-white">System health</h3>
                  <dl className="mt-4 space-y-3 text-sm">
                    {Object.entries(liveControl?.health || {}).map(([label, value]) => (
                      <div key={label} className="flex justify-between gap-4 border-b border-slate-800 pb-2">
                        <dt className="capitalize text-slate-400">{label.replace(/_/g, ' ')}</dt>
                        <dd className="font-semibold text-slate-100">{String(value)}</dd>
                      </div>
                    ))}
                  </dl>
                </div>

                <div className="card">
                  <h3 className="text-sm font-semibold text-white">Recent control changes</h3>
                  <div className="mt-4 max-h-72 space-y-3 overflow-y-auto">
                    {(liveControl?.recent_audit || []).length ? liveControl.recent_audit.map((audit: any) => (
                      <div key={audit.id} className="rounded-md border border-slate-800 px-3 py-2 text-xs text-slate-300">
                        <p className="font-semibold text-slate-100">{new Date(audit.created_at).toLocaleString()}</p>
                        <p className="mt-1 text-slate-400">{audit.changes?.reason || 'No reason recorded'}</p>
                      </div>
                    )) : <p className="text-sm text-slate-400">No owner control changes yet.</p>}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
