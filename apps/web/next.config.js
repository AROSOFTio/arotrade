/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**.arosoftlabs.com',
      },
      {
        protocol: 'https',
        hostname: 'arotrader.arosoftlabs.com',
      },
    ],
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api',
    NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME || 'AroTrade AI',
    NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT: process.env.NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT || process.env.MAX_LIVE_RISK_PERCENT || '0.25',
  },
}

module.exports = nextConfig
