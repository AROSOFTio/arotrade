import Link from 'next/link'

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-blue-950 to-slate-950">
      {/* Navigation */}
      <nav className="border-b border-slate-800 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <div className="text-2xl font-bold text-blue-400">
            🚀 AroTrade AI
          </div>
          <div className="flex gap-4">
            <Link href="/login" className="btn-secondary">
              Login
            </Link>
            <Link href="/register" className="btn-primary">
              Register
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="text-center">
          <h1 className="text-5xl md:text-6xl font-bold mb-6 text-white">
            AI-Powered Trading Intelligence
          </h1>
          <p className="text-xl text-slate-300 mb-8 max-w-2xl mx-auto">
            Analyze markets with Gemini AI, generate trading signals, test strategies, manage risk, and execute trades with confidence.
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/register" className="btn-primary text-lg px-8 py-3">
              Start Free Demo
            </Link>
            <Link href="/dashboard" className="btn-secondary text-lg px-8 py-3">
              View Dashboard
            </Link>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <h2 className="text-3xl font-bold mb-12 text-center">Features</h2>
        <div className="grid md:grid-cols-3 gap-8">
          {[
            {
              icon: '🤖',
              title: 'AI Chart Analysis',
              description: 'Upload chart screenshots and get instant AI-powered analysis with confidence levels.',
            },
            {
              icon: '📊',
              title: 'Trading Signals',
              description: 'Receive AI-generated signals with entry zones, stop loss, and profit targets.',
            },
            {
              icon: '🛠️',
              title: 'Strategy Builder',
              description: 'Create custom strategies using smart money concepts and technical indicators.',
            },
            {
              icon: '📈',
              title: 'Backtesting',
              description: 'Test strategies against historical data to validate performance before live trading.',
            },
            {
              icon: '📝',
              title: 'Trading Journal',
              description: 'Track trades, emotions, and lessons learned. Get AI feedback on your performance.',
            },
            {
              icon: '🛡️',
              title: 'Risk Guardian',
              description: 'Strict risk validation ensures no trade executes without proper stop loss.',
            },
          ].map((feature, i) => (
            <div key={i} className="card hover:border-blue-600 transition-colors">
              <div className="text-4xl mb-4">{feature.icon}</div>
              <h3 className="text-xl font-bold mb-2">{feature.title}</h3>
              <p className="text-slate-400">{feature.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Disclaimer Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 bg-red-950/20 border border-red-900/50 rounded-lg my-20">
        <h3 className="text-2xl font-bold mb-4 text-red-400">⚠️ Risk Warning</h3>
        <p className="text-slate-300 mb-4">
          <strong>AroTrade AI does not guarantee profits or win rates.</strong> Trading forex, CFDs, synthetic indices, and cryptocurrencies involves substantial risk of loss.
        </p>
        <ul className="list-disc list-inside text-slate-400 space-y-2">
          <li>Past performance does not guarantee future results</li>
          <li>Always test strategies on demo accounts first</li>
          <li>Only risk what you can afford to lose</li>
          <li>Use strict risk management and position sizing</li>
          <li>Follow all applicable regulations in your jurisdiction</li>
        </ul>
      </section>

      {/* CTA Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center">
        <h2 className="text-3xl font-bold mb-6">Ready to Start?</h2>
        <p className="text-slate-300 mb-8">Join hundreds of traders using AroTrade AI for smarter trading decisions.</p>
        <Link href="/register" className="btn-primary text-lg px-8 py-3">
          Start Free Demo Today
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-8 mt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-4 gap-8 mb-8">
            <div>
              <h4 className="font-bold mb-4">AroTrade AI</h4>
              <p className="text-slate-400 text-sm">AI-powered trading intelligence by AROSOFT Innovations.</p>
            </div>
            <div>
              <h4 className="font-bold mb-4">Product</h4>
              <ul className="space-y-2 text-slate-400 text-sm">
                <li><Link href="#" className="hover:text-white">Features</Link></li>
                <li><Link href="#" className="hover:text-white">Dashboard</Link></li>
                <li><Link href="#" className="hover:text-white">Pricing</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-bold mb-4">Legal</h4>
              <ul className="space-y-2 text-slate-400 text-sm">
                <li><Link href="#" className="hover:text-white">Terms</Link></li>
                <li><Link href="#" className="hover:text-white">Privacy</Link></li>
                <li><Link href="#" className="hover:text-white">Disclaimer</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-bold mb-4">Contact</h4>
              <ul className="space-y-2 text-slate-400 text-sm">
                <li>support@arotrade.com</li>
                <li>Made by AROSOFT</li>
              </ul>
            </div>
          </div>
          <div className="border-t border-slate-800 pt-8 text-center text-slate-500 text-sm">
            <p>&copy; 2024 AroTrade AI. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
