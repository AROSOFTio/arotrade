'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function HomePage() {
  const router = useRouter()

  useEffect(() => {
    router.replace(window.localStorage.getItem('access_token') ? '/dashboard' : '/login')
  }, [router])

  return <div className="flex min-h-screen items-center justify-center bg-[#f6f7f9] text-sm font-medium text-slate-500">Opening AroTrade…</div>
}
