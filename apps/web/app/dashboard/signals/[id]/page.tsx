import { redirect } from 'next/navigation'

export default function SignalDeepLinkPage({ params }: { params: { id: string } }) {
  redirect(`/dashboard/signals?signal=${encodeURIComponent(params.id)}`)
}
