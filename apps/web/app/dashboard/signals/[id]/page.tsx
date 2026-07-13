import { redirect } from 'next/navigation'

export default async function SignalDeepLinkPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  redirect(`/dashboard/signals?signal=${encodeURIComponent(id)}`)
}
