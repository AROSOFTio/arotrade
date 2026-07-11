'use client'

import { useEffect, useState } from 'react'
import { Landmark, Plus, Power } from 'lucide-react'

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
}

export default function BrokerAccountsPage() {
  const [accounts, setAccounts] = useState<BrokerAccount[]>([])
  const [form, setForm] = useState({ broker: 'mt5', account_id: '', balance: '', currency: 'USD' })
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadAccounts = async () => {
    setLoading(true)
    try { setAccounts(await apiRequest<BrokerAccount[]>('/broker-accounts')) } catch (requestError) { setError(errorMessage(requestError)) } finally { setLoading(false) }
  }

  useEffect(() => { void loadAccounts() }, [])

  const addAccount = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setSubmitting(true)
    try {
      const account = await apiRequest<BrokerAccount>('/broker-accounts', { method: 'POST', body: JSON.stringify({ broker: form.broker, account_id: form.account_id, balance: form.balance ? Number(form.balance) : 0, currency: form.currency }) })
      setAccounts((current) => [account, ...current])
      setForm((current) => ({ ...current, account_id: '', balance: '' }))
      setMessage('Demo account record added.')
    } catch (requestError) { setError(errorMessage(requestError)) } finally { setSubmitting(false) }
  }

  const deactivate = async (accountId: number) => {
    setError('')
    setMessage('')
    try {
      const account = await apiRequest<BrokerAccount>(`/broker-accounts/${accountId}/deactivate`, { method: 'POST' })
      setAccounts((current) => current.map((item) => item.id === account.id ? account : item))
      setMessage('Demo account record deactivated.')
    } catch (requestError) { setError(errorMessage(requestError)) }
  }

  return (
    <>
      <PageHeader eyebrow="Account context" title="Demo accounts" description="Keep paper-account metadata in the workspace. Broker credentials and live account connections are intentionally not stored here." />
      {(error || message) && <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>{error || message}</div>}
      <section className="grid gap-6 xl:grid-cols-[minmax(340px,0.7fr)_minmax(0,1.3fr)]"><form onSubmit={addAccount} className="card h-fit"><div className="flex items-center gap-2"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><Plus size={18} aria-hidden="true" /></span><div><h2 className="text-sm font-semibold text-slate-900">Add demo account</h2><p className="mt-0.5 text-xs text-slate-500">Metadata only. No API token or password is accepted.</p></div></div><div className="mt-5"><label htmlFor="broker-name" className="label">Platform / broker</label><input id="broker-name" className="input-base" value={form.broker} onChange={(event) => setForm((current) => ({ ...current, broker: event.target.value }))} required /></div><div className="mt-4"><label htmlFor="account-id" className="label">Demo account ID</label><input id="account-id" className="input-base" value={form.account_id} onChange={(event) => setForm((current) => ({ ...current, account_id: event.target.value }))} required /></div><div className="mt-4 grid grid-cols-2 gap-4"><div><label htmlFor="starting-balance" className="label">Reference balance</label><input id="starting-balance" type="number" min="0" step="any" className="input-base" value={form.balance} onChange={(event) => setForm((current) => ({ ...current, balance: event.target.value }))} /></div><div><label htmlFor="currency" className="label">Currency</label><input id="currency" maxLength={3} className="input-base uppercase" value={form.currency} onChange={(event) => setForm((current) => ({ ...current, currency: event.target.value.toUpperCase() }))} required /></div></div><button type="submit" disabled={submitting} className="btn-primary mt-5 w-full">{submitting ? 'Adding…' : 'Add demo account'}</button></form><div className="card overflow-hidden p-0"><div className="border-b border-slate-200 px-5 py-4"><h2 className="text-sm font-semibold text-slate-900">Account records</h2><p className="mt-1 text-xs text-slate-500">These entries do not create a broker connection.</p></div>{loading ? <div className="p-8 text-sm text-slate-500">Loading account records…</div> : accounts.length ? <div className="divide-y divide-slate-100">{accounts.map((account) => <div key={account.id} className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="text-sm font-semibold capitalize text-slate-900">{account.broker} <span className="font-normal text-slate-500">· {account.account_id}</span></h3><p className="mt-1 text-sm text-slate-600">{formatNumber(account.balance)} {account.currency} reference balance</p><p className="mt-1 text-xs text-slate-500">Added {formatDate(account.created_at)}</p></div><div className="flex items-center gap-3"><StatusBadge value={account.is_active ? 'active' : 'inactive'} />{account.is_active && <button type="button" onClick={() => void deactivate(account.id)} className="icon-button text-slate-600" title={`Deactivate ${account.broker} account`}><Power size={17} aria-hidden="true" /></button>}</div></div>)}</div> : <EmptyState icon={Landmark} title="No demo accounts" description="Add a non-sensitive demo-account reference to give the paper workspace useful context." />}</div></section>
    </>
  )
}
