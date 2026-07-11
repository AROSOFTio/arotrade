'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { CircleUserRound, ExternalLink, ShieldCheck } from 'lucide-react'

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

export default function SettingsPage() {
  const [user, setUser] = useState<User | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiRequest<User>('/auth/me').then(setUser).catch((requestError) => setError(errorMessage(requestError)))
  }, [])

  return (
    <>
      <PageHeader eyebrow="Account" title="Settings" description="Account identity and platform state for this workspace." />
      {error && <div className="mb-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      <section className="grid gap-6 lg:grid-cols-2"><div className="card"><div className="flex items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-900 text-white"><CircleUserRound size={22} aria-hidden="true" /></span><div><h2 className="text-base font-semibold text-slate-900">{user?.full_name || 'Account profile'}</h2><p className="mt-1 text-sm text-slate-500">{user?.email || 'Loading account…'}</p></div></div><dl className="mt-6 divide-y divide-slate-100 text-sm"><div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Role</dt><dd className="font-semibold capitalize text-slate-900">{user?.role || '—'}</dd></div><div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Account status</dt><dd className="font-semibold text-slate-900">{user?.is_active ? 'Active' : 'Inactive'}</dd></div><div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Member since</dt><dd className="font-semibold text-slate-900">{formatDate(user?.created_at)}</dd></div></dl></div><div className="card"><div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><ShieldCheck size={20} aria-hidden="true" /></div><h2 className="mt-4 text-base font-semibold text-slate-900">Execution profile</h2><dl className="mt-4 divide-y divide-slate-100 text-sm"><div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Workspace mode</dt><dd className="font-semibold capitalize text-[#1d4ed8]">{user?.trading_mode || 'Demo'}</dd></div><div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Live trading</dt><dd className="font-semibold text-slate-900">{user?.enable_live_trading ? 'Allowed' : 'Locked'}</dd></div><div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Broker adapter</dt><dd className="font-semibold text-slate-900">Not connected</dd></div></dl><Link href="/dashboard/risk" className="btn-secondary mt-5">Open risk controls <ExternalLink size={16} aria-hidden="true" /></Link></div></section>
    </>
  )
}
