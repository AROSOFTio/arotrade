'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { CircleUserRound, ExternalLink, ShieldCheck, TriangleAlert } from 'lucide-react'

import { apiRequest, errorMessage, formatDate } from '../../components/api'
import { PageHeader } from '../../components/page-header'

type User = {
  email: string
  full_name?: string | null
  role: string
  trading_mode: string
  enable_live_trading: boolean
  is_active: boolean
  created_at: string
}

type BrokerAccount = {
  id: number
  account_id: string
  account_type: string
  server?: string | null
  connection_state?: string | null
  metaapi_account_id?: string | null
  is_active: boolean
}

export default function SettingsPage() {
  const [user, setUser] = useState<User | null>(null)
  const [brokerAccounts, setBrokerAccounts] = useState<BrokerAccount[]>([])
  const [error, setError] = useState('')
  const [showConsent, setShowConsent] = useState(false)
  const [consentChecked, setConsentChecked] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([
      apiRequest<User>('/auth/me'),
      apiRequest<BrokerAccount[]>('/broker-accounts'),
    ])
      .then(([nextUser, nextBrokerAccounts]) => {
        setUser(nextUser)
        setBrokerAccounts(nextBrokerAccounts)
      })
      .catch((requestError) => setError(errorMessage(requestError)))
  }, [])

  const updateLiveTrading = async (enable: boolean, acceptDisclaimer = false) => {
    setSaving(true)
    setError('')
    try {
      const updated = await apiRequest<User>('/auth/me/live-trading', {
        method: 'PATCH',
        body: JSON.stringify({ enable, accept_risk_disclaimer: acceptDisclaimer }),
      })
      setUser(updated)
      setShowConsent(false)
      setConsentChecked(false)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  const workspaceMode = user?.enable_live_trading && user.trading_mode?.toLowerCase() === 'live' ? 'Live' : 'Demo'
  const deployedAccounts = brokerAccounts.filter((account) =>
    account.is_active && account.metaapi_account_id && account.connection_state === 'deployed'
  )
  const liveBroker = deployedAccounts.find((account) => account.account_type?.toLowerCase() === 'live')
  const brokerAdapter = liveBroker || deployedAccounts[0]
  const brokerAdapterLabel = brokerAdapter ? `${brokerAdapter.account_type.toUpperCase()} connected` : 'Not connected'

  return (
    <>
      <PageHeader eyebrow="Account" title="Settings" description="Account identity and platform state for this workspace." />
      {error && <div className="mb-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      <section className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-900 text-white"><CircleUserRound size={22} aria-hidden="true" /></span>
            <div>
              <h2 className="text-base font-semibold text-slate-900">{user?.full_name || 'Account profile'}</h2>
              <p className="mt-1 text-sm text-slate-500">{user?.email || 'Loading account…'}</p>
            </div>
          </div>
          <dl className="mt-6 divide-y divide-slate-100 text-sm">
            <div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Role</dt><dd className="font-semibold capitalize text-slate-900">{user?.role || '—'}</dd></div>
            <div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Account status</dt><dd className="font-semibold text-slate-900">{user?.is_active ? 'Active' : 'Inactive'}</dd></div>
            <div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Member since</dt><dd className="font-semibold text-slate-900">{formatDate(user?.created_at)}</dd></div>
          </dl>
        </div>

        <div className="card">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><ShieldCheck size={20} aria-hidden="true" /></div>
          <h2 className="mt-4 text-base font-semibold text-slate-900">Execution profile</h2>
          <dl className="mt-4 divide-y divide-slate-100 text-sm">
            <div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Workspace mode</dt><dd className={`font-semibold ${workspaceMode === 'Live' ? 'text-[#15803d]' : 'text-[#1d4ed8]'}`}>{workspaceMode}</dd></div>
            <div className="flex items-center justify-between gap-4 py-3">
              <dt className="text-slate-500">Live trading</dt>
              <dd className="flex items-center gap-3">
                <span className={`font-semibold ${user?.enable_live_trading ? 'text-[#15803d]' : 'text-slate-900'}`}>{user?.enable_live_trading ? 'Enabled' : 'Off'}</span>
                {user && (
                  user.enable_live_trading ? (
                    <button type="button" disabled={saving} className="btn-secondary min-h-8 px-3 py-1 text-xs" onClick={() => updateLiveTrading(false)}>Turn off</button>
                  ) : (
                    <button type="button" disabled={saving} className="btn-secondary min-h-8 px-3 py-1 text-xs" onClick={() => setShowConsent(true)}>Enable</button>
                  )
                )}
              </dd>
            </div>
            <div className="flex justify-between gap-4 py-3">
              <dt className="text-slate-500">Broker adapter</dt>
              <dd className="text-right">
                <span className={`font-semibold ${brokerAdapter ? 'text-[#15803d]' : 'text-slate-900'}`}>{brokerAdapterLabel}</span>
                {brokerAdapter && (
                  <span className="mt-0.5 block text-xs font-medium text-slate-500">{brokerAdapter.account_id}{brokerAdapter.server ? ` - ${brokerAdapter.server}` : ''}</span>
                )}
              </dd>
            </div>
          </dl>
          <p className="mt-3 text-xs leading-5 text-slate-500">
            Live trading is your choice. Enabling it records your consent; live orders start flowing once a broker adapter (MT5 / Deriv) is connected to your account.
          </p>
          <Link href="/dashboard/risk" className="btn-secondary mt-5">Open risk controls <ExternalLink size={16} aria-hidden="true" /></Link>
        </div>
      </section>

      {showConsent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Live trading risk disclaimer">
          <button type="button" className="absolute inset-0 bg-slate-950/40" onClick={() => setShowConsent(false)} aria-label="Close dialog" />
          <div className="card relative w-full max-w-lg">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-amber-50 text-amber-700"><TriangleAlert size={22} aria-hidden="true" /></div>
            <h2 className="mt-4 text-lg font-bold text-slate-950">Enable live trading</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Live trading uses real money. Losses can exceed your expectations, markets can gap through stop losses, and AI analysis can be wrong.
              Your platform risk limits (max risk per trade, daily loss cap, drawdown guard) stay enforced on every order.
            </p>
            <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-700">
              <input type="checkbox" className="mt-0.5 h-4 w-4 cursor-pointer accent-[#2563eb]" checked={consentChecked} onChange={(e) => setConsentChecked(e.target.checked)} />
              I understand the risks of live trading, I accept full responsibility for my trades, and I accept the risk disclaimer.
            </label>
            <div className="mt-5 flex items-center justify-end gap-3">
              <button type="button" className="btn-secondary" onClick={() => setShowConsent(false)}>Cancel</button>
              <button type="button" className="btn-primary" disabled={!consentChecked || saving} onClick={() => updateLiveTrading(true, true)}>
                {saving ? 'Saving…' : 'Enable live trading'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
