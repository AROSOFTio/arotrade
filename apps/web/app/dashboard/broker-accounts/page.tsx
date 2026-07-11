'use client'

import { useCallback, useEffect, useState } from 'react'
import { Landmark, Link2, Power, RefreshCw, Rocket, Square } from 'lucide-react'

import { apiRequest, errorMessage, formatDate, formatNumber } from '../../components/api'
import { EmptyState } from '../../components/empty-state'
import { PageHeader } from '../../components/page-header'
import { StatusBadge } from '../../components/status-badge'

type BrokerAccount = {
  id: number
  broker: string
  account_id: string
  account_type: string
  balance: number
  currency: string
  is_active: boolean
  created_at: string
  name?: string | null
  server?: string | null
  platform?: string | null
  connection_state?: string | null
  metaapi_account_id?: string | null
}

const initialForm = { name: '', login: '', password: '', server: '', platform: 'mt5', account_type: 'demo' }

function stateTone(state?: string | null) {
  if (state === 'deployed') return 'bg-[#f0fdf4] text-[#15803d]'
  if (state === 'deploying' || state === 'undeploying') return 'bg-amber-50 text-amber-700'
  return 'bg-slate-100 text-slate-600'
}

export default function BrokerAccountsPage() {
  const [accounts, setAccounts] = useState<BrokerAccount[]>([])
  const [form, setForm] = useState(initialForm)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const refreshAccountStates = useCallback(async (initialAccounts: BrokerAccount[]) => {
    const refreshableAccounts = initialAccounts.filter((account) => account.metaapi_account_id && account.is_active)
    if (!refreshableAccounts.length) return

    const results = await Promise.allSettled(
      refreshableAccounts.map((account) => apiRequest<BrokerAccount>(`/broker-accounts/${account.id}/state`)),
    )
    const refreshedAccounts = results
      .filter((result): result is PromiseFulfilledResult<BrokerAccount> => result.status === 'fulfilled')
      .map((result) => result.value)

    if (refreshedAccounts.length) {
      setAccounts((current) => current.map((account) => refreshedAccounts.find((item) => item.id === account.id) || account))
    }
  }, [])

  const loadAccounts = useCallback(async () => {
    setLoading(true)
    try {
      const nextAccounts = await apiRequest<BrokerAccount[]>('/broker-accounts')
      setAccounts(nextAccounts)
      void refreshAccountStates(nextAccounts)
    } catch (requestError) { setError(errorMessage(requestError)) } finally { setLoading(false) }
  }, [refreshAccountStates])

  useEffect(() => { void loadAccounts() }, [loadAccounts])

  const connectMt5 = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setSubmitting(true)
    try {
      const account = await apiRequest<BrokerAccount>('/broker-accounts/mt5', { method: 'POST', body: JSON.stringify(form) })
      setAccounts((current) => [account, ...current])
      setForm(initialForm)
      setMessage('Account registered with MetaApi. Press Deploy to start the connection (hourly billing runs only while deployed).')
    } catch (requestError) { setError(errorMessage(requestError)) } finally { setSubmitting(false) }
  }

  const accountAction = async (accountId: number, action: 'deploy' | 'undeploy' | 'state' | 'deactivate') => {
    setError('')
    setMessage('')
    setBusyId(accountId)
    try {
      const path = action === 'state' ? `/broker-accounts/${accountId}/state` : `/broker-accounts/${accountId}/${action}`
      const account = await apiRequest<BrokerAccount>(path, { method: action === 'state' ? 'GET' : 'POST' })
      setAccounts((current) => current.map((item) => item.id === account.id ? account : item))
      if (action === 'deploy') setMessage('Deploying — the broker connection usually takes 1–3 minutes. Use Refresh to check.')
      if (action === 'undeploy') setMessage('Undeploying — hourly billing stops once undeployed.')
      if (action === 'state') setMessage('State refreshed.')
    } catch (requestError) { setError(errorMessage(requestError)) } finally { setBusyId(null) }
  }

  return (
    <>
      <PageHeader
        eyebrow="Brokers"
        title="Broker accounts"
        description="Connect your MT5 account (Exness or any MT5 broker) through MetaApi. Deploy to go online; undeploy any time to stop connection billing."
      />
      {(error || message) && <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>{error || message}</div>}
      <section className="grid gap-6 xl:grid-cols-[minmax(340px,0.7fr)_minmax(0,1.3fr)]">
        <form onSubmit={connectMt5} className="card h-fit">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><Link2 size={18} aria-hidden="true" /></span>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Connect MT5 / Exness account</h2>
              <p className="mt-0.5 text-xs text-slate-500">Credentials go straight to MetaApi — never stored on AroTrader.</p>
            </div>
          </div>
          <div className="mt-5">
            <label htmlFor="acc-name" className="label">Account nickname</label>
            <input id="acc-name" className="input-base" value={form.name} onChange={(e) => setForm((c) => ({ ...c, name: e.target.value }))} required placeholder="Exness demo" />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="acc-login" className="label">MT5 login (account no.)</label>
              <input id="acc-login" className="input-base" value={form.login} onChange={(e) => setForm((c) => ({ ...c, login: e.target.value.replace(/\D/g, '') }))} required inputMode="numeric" pattern="[0-9]*" placeholder="134478618" title="Use the MT5 login/account number, not your Exness email address." />
              <p className="mt-1.5 text-xs text-slate-500">Use the MT5 login/account number, not your Exness email.</p>
            </div>
            <div>
              <label htmlFor="acc-platform" className="label">Platform</label>
              <select id="acc-platform" className="input-base" value={form.platform} onChange={(e) => setForm((c) => ({ ...c, platform: e.target.value }))}>
                <option value="mt5">MT5</option>
                <option value="mt4">MT4</option>
              </select>
            </div>
          </div>
          <div className="mt-4">
            <label htmlFor="acc-password" className="label">Trading password</label>
            <input id="acc-password" type="password" autoComplete="off" className="input-base" value={form.password} onChange={(e) => setForm((c) => ({ ...c, password: e.target.value }))} required />
            <p className="mt-1.5 text-xs text-slate-500">Use the main trading password, not the read-only investor password.</p>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="acc-server" className="label">Broker server</label>
              <input id="acc-server" className="input-base" value={form.server} onChange={(e) => setForm((c) => ({ ...c, server: e.target.value }))} required placeholder="Exness-MT5Trial7" />
            </div>
            <div>
              <label htmlFor="acc-type" className="label">Account type</label>
              <select id="acc-type" className="input-base" value={form.account_type} onChange={(e) => setForm((c) => ({ ...c, account_type: e.target.value }))}>
                <option value="demo">Demo</option>
                <option value="live">Live (real money)</option>
              </select>
            </div>
          </div>
          <button type="submit" disabled={submitting} className="btn-primary mt-5 w-full">{submitting ? 'Connecting…' : 'Connect account'}</button>
        </form>

        <div className="card overflow-hidden p-0">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-sm font-semibold text-slate-900">Connected accounts</h2>
            <p className="mt-1 text-xs text-slate-500">Deploy = online and billable per hour on MetaApi. Undeploy = offline, billing stopped.</p>
          </div>
          {loading ? <div className="p-8 text-sm text-slate-500">Loading accounts…</div> : accounts.length ? (
            <div className="divide-y divide-slate-100">
              {accounts.map((account) => (
                <div key={account.id} className="flex flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-slate-900">
                      {account.name || account.broker} <span className="font-normal text-slate-500">· {account.account_id}{account.server ? ` · ${account.server}` : ''}</span>
                    </h3>
                    <p className="mt-1 text-sm text-slate-600">{formatNumber(account.balance)} {account.currency} · <span className="uppercase">{account.account_type}</span></p>
                    <p className="mt-1 text-xs text-slate-500">Added {formatDate(account.created_at)}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {account.metaapi_account_id ? (
                      <>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${stateTone(account.connection_state)}`}>{account.connection_state || 'unknown'}</span>
                        {account.connection_state === 'deployed' || account.connection_state === 'deploying' ? (
                          <button type="button" disabled={busyId === account.id} onClick={() => void accountAction(account.id, 'undeploy')} className="btn-secondary min-h-8 px-3 py-1 text-xs">
                            <Square size={13} aria-hidden="true" /> Undeploy
                          </button>
                        ) : (
                          <button type="button" disabled={busyId === account.id} onClick={() => void accountAction(account.id, 'deploy')} className="btn-primary min-h-8 px-3 py-1 text-xs">
                            <Rocket size={13} aria-hidden="true" /> Deploy
                          </button>
                        )}
                        <button type="button" disabled={busyId === account.id} onClick={() => void accountAction(account.id, 'state')} className="icon-button h-8 w-8" title="Refresh state">
                          <RefreshCw size={14} aria-hidden="true" className={busyId === account.id ? 'animate-spin' : ''} />
                        </button>
                      </>
                    ) : (
                      <StatusBadge value={account.is_active ? 'active' : 'inactive'} />
                    )}
                    {account.is_active && (
                      <button type="button" onClick={() => void accountAction(account.id, 'deactivate')} className="icon-button h-8 w-8 text-slate-600" title="Deactivate account">
                        <Power size={14} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={Landmark} title="No broker accounts" description="Connect your Exness or other MT5 account to enable live execution. Start with a demo account." />
          )}
        </div>
      </section>
    </>
  )
}
