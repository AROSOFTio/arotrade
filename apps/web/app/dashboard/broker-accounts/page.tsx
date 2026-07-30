'use client'

import { useCallback, useEffect, useState } from 'react'
import { Copy, Download, Landmark, PlugZap, Trash2 } from 'lucide-react'

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
}

const initialDirectForm = { name: 'Local MT5 terminal', login: '', server: '', account_type: 'demo' }

function stateTone(state?: string | null) {
  if (state === 'direct_connected') return 'bg-[#f0fdf4] text-[#15803d]'
  if (state === 'waiting_for_ea') return 'bg-blue-50 text-[#1d4ed8]'
  return 'bg-slate-100 text-slate-600'
}

export default function BrokerAccountsPage() {
  const [accounts, setAccounts] = useState<BrokerAccount[]>([])
  const [directForm, setDirectForm] = useState(initialDirectForm)
  const [bridgeKey, setBridgeKey] = useState('')
  const [bridgeAccountId, setBridgeAccountId] = useState<number | null>(null)
  const [bridgeEndpoint, setBridgeEndpoint] = useState('https://arotrader.arosoftlabs.com/api/mt5/bridge')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadAccounts = useCallback(async () => {
    setLoading(true)
    try {
      setAccounts(await apiRequest<BrokerAccount[]>('/broker-accounts'))
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadAccounts() }, [loadAccounts])

  const createDirectBridge = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setBridgeKey('')
    setSubmitting(true)
    try {
      const response = await apiRequest<{ account: BrokerAccount; api_key: string; endpoint: string }>('/broker-accounts/direct-mt5', {
        method: 'POST',
        body: JSON.stringify(directForm),
      })
      setAccounts((current) => [response.account, ...current])
      setBridgeKey(response.api_key)
      setBridgeAccountId(response.account.id)
      setBridgeEndpoint(response.endpoint)
      setMessage('Direct MT5 bridge created. Paste the endpoint, account id and bridge key into the MT5 Expert Advisor.')
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  const showDirectBridgeInputs = async (account: BrokerAccount) => {
    setError('')
    setMessage('')
    setBusyId(account.id)
    try {
      const response = await apiRequest<{ account_id: number; api_key: string; endpoint: string }>(`/broker-accounts/direct-mt5/${account.id}/credentials`)
      setBridgeKey(response.api_key)
      setBridgeAccountId(response.account_id)
      setBridgeEndpoint(response.endpoint)
      setMessage('EA inputs loaded. Copy them into the AroPilotEA Inputs tab in MetaTrader.')
      window.setTimeout(() => {
        document.getElementById('ea-inputs-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 50)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setBusyId(null)
    }
  }

  const deleteAccount = async (account: BrokerAccount) => {
    const label = account.name || account.account_id
    if (!window.confirm(`Delete "${label}"? Historical trades and analyses will be retained, but this connection cannot be restored.`)) return
    setError('')
    setMessage('')
    setBusyId(account.id)
    try {
      await apiRequest<{ status: string; account_id: number }>(`/broker-accounts/${account.id}`, { method: 'DELETE' })
      setAccounts((current) => current.filter((item) => item.id !== account.id))
      setMessage('Broker account deleted.')
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Brokers"
        title="Broker accounts"
        description="Connect MetaTrader 5 through the AroPilot Expert Advisor. Direct MT5 is now the only live bridge."
      />
      {(error || message) && (
        <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
          {error || message}
        </div>
      )}

      <section className="grid gap-6 xl:grid-cols-[minmax(340px,0.7fr)_minmax(0,1.3fr)]">
        <div className="space-y-6">
          <form onSubmit={createDirectBridge} className="card h-fit">
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-[#16a34a]"><PlugZap size={18} aria-hidden="true" /></span>
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Direct MT5 bridge</h2>
                <p className="mt-0.5 text-xs text-slate-500">Use AroPilotEA in MetaTrader for live quotes, candles, chart drawings, orders, SL/TP updates, and account state.</p>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="direct-name" className="label">Bridge name</label>
                <input id="direct-name" className="input-base" value={directForm.name} onChange={(e) => setDirectForm((c) => ({ ...c, name: e.target.value }))} required />
              </div>
              <div>
                <label htmlFor="direct-type" className="label">Account type</label>
                <select id="direct-type" className="input-base" value={directForm.account_type} onChange={(e) => setDirectForm((c) => ({ ...c, account_type: e.target.value }))}>
                  <option value="demo">Demo</option>
                  <option value="live">Live</option>
                </select>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="direct-login" className="label">MT5 login</label>
                <input id="direct-login" className="input-base" value={directForm.login} onChange={(e) => setDirectForm((c) => ({ ...c, login: e.target.value.replace(/\D/g, '') }))} placeholder="134478618" />
              </div>
              <div>
                <label htmlFor="direct-server" className="label">Broker server</label>
                <input id="direct-server" className="input-base" value={directForm.server} onChange={(e) => setDirectForm((c) => ({ ...c, server: e.target.value }))} placeholder="Exness-MT5Real9" />
              </div>
            </div>

            <button type="submit" disabled={submitting} className="btn-primary mt-5 w-full">{submitting ? 'Creating...' : 'Create direct MT5 bridge'}</button>
            <a href="/mt5/AroPilotMT5Connector.zip" download className="mt-3 flex min-h-10 w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"><Download size={15} /> Download MT5 connector</a>

            {bridgeKey && (
              <div id="ea-inputs-card" className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">
                <div className="font-bold">EA inputs</div>
                <p className="mt-1 text-[11px] leading-5 text-emerald-800">Paste these values into AroPilotEA Inputs. AccountId must not be 0 and ApiKey must not be empty.</p>
                <div className="mt-2 space-y-1 font-mono break-all">
                  <div>BridgeUrl={bridgeEndpoint}</div>
                  <div>AccountId={bridgeAccountId}</div>
                  <div>ApiKey={bridgeKey}</div>
                </div>
                <button type="button" className="mt-3 inline-flex items-center gap-2 text-xs font-bold text-emerald-800" onClick={() => void navigator.clipboard?.writeText(`BridgeUrl=${bridgeEndpoint}\nAccountId=${bridgeAccountId}\nApiKey=${bridgeKey}`)}><Copy size={13} /> Copy inputs</button>
              </div>
            )}
          </form>
        </div>

        <div className="card overflow-hidden p-0">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-sm font-semibold text-slate-900">Connected accounts</h2>
            <p className="mt-1 text-xs text-slate-500">Direct MT5 bridge accounts are active. Old hosted-adapter rows can be deleted, but cannot be deployed or refreshed.</p>
          </div>

          {loading ? (
            <div className="p-8 text-sm text-slate-500">Loading accounts...</div>
          ) : accounts.length ? (
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
                    {!account.is_active ? (
                      <StatusBadge value="inactive" />
                    ) : account.broker === 'direct-mt5' ? (
                      <>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${stateTone(account.connection_state)}`}>{account.connection_state || 'waiting_for_ea'}</span>
                        <button type="button" disabled={busyId === account.id} onClick={() => void showDirectBridgeInputs(account)} className="btn-secondary min-h-8 px-3 py-1 text-xs">
                          <Copy size={13} aria-hidden="true" /> Show EA inputs
                        </button>
                      </>
                    ) : (
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">legacy adapter disabled</span>
                    )}
                    <button type="button" disabled={busyId === account.id} onClick={() => void deleteAccount(account)} className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1 text-xs font-semibold text-red-700 hover:bg-red-50">
                      <Trash2 size={13} aria-hidden="true" /> Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={Landmark} title="No broker accounts" description="Create a direct MT5 bridge, paste the EA inputs into MetaTrader, and keep the EA attached to a chart." />
          )}
        </div>
      </section>
    </>
  )
}
