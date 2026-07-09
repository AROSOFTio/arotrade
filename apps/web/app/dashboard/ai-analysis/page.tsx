'use client'

import { useState } from 'react'
import axios from 'axios'

export default function AIAnalysisPage() {
  const [symbol, setSymbol] = useState('EURUSD')
  const [timeframe, setTimeframe] = useState('M15')
  const [prompt, setPrompt] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [analysis, setAnalysis] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const token = localStorage.getItem('access_token')

      const response = await axios.post(
        `${process.env.NEXT_PUBLIC_API_URL}/ai/analyze`,
        {
          symbol,
          timeframe,
          prompt: prompt || 'Analyze this chart for trading opportunities',
          image_url: file ? URL.createObjectURL(file) : null,
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      )

      setAnalysis(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">AI Chart Analysis</h1>

        <div className="grid lg:grid-cols-2 gap-8">
          {/* Form */}
          <div className="card">
            <h2 className="text-xl font-bold mb-6">Upload Chart</h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Symbol</label>
                  <input
                    type="text"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    className="input-base"
                    placeholder="EURUSD"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Timeframe</label>
                  <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="input-base">
                    <option>M1</option>
                    <option>M5</option>
                    <option>M15</option>
                    <option>M30</option>
                    <option>H1</option>
                    <option>H4</option>
                    <option>D1</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Chart Image</label>
                <div className="border-2 border-dashed border-slate-700 rounded-lg p-6 text-center">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                    className="hidden"
                    id="file-input"
                  />
                  <label htmlFor="file-input" className="cursor-pointer">
                    <div className="text-4xl mb-2">📸</div>
                    <p className="text-slate-400">Click to upload or paste image</p>
                    {file && <p className="text-blue-400 mt-2">{file.name}</p>}
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Analysis Prompt (Optional)</label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="input-base"
                  placeholder="Enter specific instructions for AI analysis"
                  rows={3}
                />
              </div>

              {error && (
                <div className="p-4 bg-red-900/20 border border-red-900/50 rounded-lg text-red-300">
                  {error}
                </div>
              )}

              <button type="submit" disabled={loading} className="w-full btn-primary py-3 disabled:opacity-50">
                {loading ? 'Analyzing...' : 'Analyze with AI'}
              </button>
            </form>
          </div>

          {/* Results */}
          {analysis && (
            <div className="card">
              <h2 className="text-xl font-bold mb-6">Analysis Result</h2>

              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Signal</span>
                  <span className={`px-3 py-1 rounded font-bold ${analysis.signal === 'buy' ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
                    {analysis.signal?.toUpperCase()}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Confidence</span>
                  <span className="font-bold">{analysis.confidence}%</span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Bias</span>
                  <span className="font-bold capitalize">{analysis.bias}</span>
                </div>

                <div className="border-t border-slate-700 pt-4 mt-4">
                  <p className="text-sm text-slate-400 mb-2">Entry Zone</p>
                  <p className="font-bold">{analysis.entry_min?.toFixed(2)} - {analysis.entry_max?.toFixed(2)}</p>
                </div>

                <div>
                  <p className="text-sm text-slate-400 mb-2">Stop Loss</p>
                  <p className="font-bold text-red-400">{analysis.stop_loss?.toFixed(2)}</p>
                </div>

                <div>
                  <p className="text-sm text-slate-400 mb-2">Take Profits</p>
                  <div className="space-y-1">
                    {[analysis.take_profit_1, analysis.take_profit_2, analysis.take_profit_3]
                      .filter(Boolean)
                      .map((tp, i) => (
                        <p key={i} className="font-bold text-green-400">
                          TP{i + 1}: {tp?.toFixed(2)}
                        </p>
                      ))}
                  </div>
                </div>

                <div>
                  <p className="text-sm text-slate-400 mb-2">Risk/Reward</p>
                  <p className="font-bold text-blue-400">{analysis.risk_reward?.toFixed(2)}:1</p>
                </div>

                {analysis.risk_warning && (
                  <div className="p-3 bg-yellow-900/20 border border-yellow-900/50 rounded text-yellow-300 text-sm">
                    {analysis.risk_warning}
                  </div>
                )}

                {analysis.news_warning && (
                  <div className="p-3 bg-yellow-900/20 border border-yellow-900/50 rounded text-yellow-300 text-sm">
                    {analysis.news_warning}
                  </div>
                )}

                <button className="w-full btn-primary py-2 mt-4">
                  Create Signal from This Analysis
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
