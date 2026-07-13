'use client'

import { useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'

export default function SignalDeepLinkPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()

  useEffect(() => {
    if (params.id) {
      window.localStorage.setItem('arotrade:selected_signal_id', params.id)
    }
    router.replace('/dashboard/signals')
  }, [params.id, router])

  return null
}