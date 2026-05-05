import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { startReview, connectLogsWebSocket } from '../api'
import { Bug, Shield, Zap, Target, Loader2, Play } from 'lucide-react'

const DOMAINS = ['correctness', 'security', 'performance', 'test_coverage']
const DOMAIN_ICONS = { correctness: <Bug size={16}/>, security: <Shield size={16}/>, performance: <Zap size={16}/>, test_coverage: <Target size={16}/> }
const MODELS = [
  { value: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B (Groq Fast)' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini (Recommended)' },
  { value: 'gpt-4o', label: 'GPT-4o (Best Quality)' },
  { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku (Fast)' },
  { value: 'claude-3-sonnet-20240229', label: 'Claude 3 Sonnet' },
  { value: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
]

export default function NewReview() {
  const navigate = useNavigate()
  const [prUrl, setPrUrl] = useState('')
  const [domains, setDomains] = useState({ correctness: true, security: true, performance: true, test_coverage: true })
  const [minConfidence, setMinConfidence] = useState('MEDIUM')
  const [model, setModel] = useState('llama-3.1-8b-instant')
  const [dryRun, setDryRun] = useState(false)
  const [synthesis, setSynthesis] = useState(true)
  const [githubToken, setGithubToken] = useState('')
  const [running, setRunning] = useState(false)
  const [runId, setRunId] = useState(null)
  const [logs, setLogs] = useState([])
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)
  const logsEndRef = useRef(null)
  const wsRef = useRef(null)

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  useEffect(() => {
    return () => wsRef.current?.close()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!prUrl.trim()) return
    setError(null)
    setLogs([])
    setDone(false)
    setRunning(true)

    const config = {
      domains,
      min_confidence: minConfidence,
      dry_run: dryRun,
      model,
      synthesis_pass: synthesis,
      ...(githubToken ? { github_token: githubToken } : {}),
    }

    try {
      const result = await startReview(prUrl.trim(), config)
      setRunId(result.run_id)

      // Connect WebSocket for live logs
      const ws = connectLogsWebSocket(
        result.run_id,
        (entry) => setLogs(prev => [...prev, { ...entry, ts: new Date().toLocaleTimeString() }]),
        () => {
          setDone(true)
          setRunning(false)
        },
      )
      wsRef.current = ws
    } catch (err) {
      setError(err.message)
      setRunning(false)
    }
  }

  const logLevelColor = {
    info: 'var(--text-secondary)',
    success: '#4ade80',
    warning: '#fbbf24',
    error: '#f87171',
    debug: 'var(--text-muted)',
  }

  return (
    <div className="animate-in">
      <div className="mb-6">
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: 4 }}>New Code Review</h2>
        <p className="text-sm text-muted">Analyze a GitHub PR with AI-powered multi-domain review</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: running ? '1fr 1fr' : '1fr', gap: 24 }}>
        {/* Config form */}
        <form onSubmit={handleSubmit}>
          <div className="card">
            <div className="card-header">
              <span className="card-title">🔗 PR URL</span>
            </div>
            <div className="input-group mb-4">
              <input
                className="input"
                type="url"
                placeholder="https://github.com/owner/repo/pull/123"
                value={prUrl}
                onChange={e => setPrUrl(e.target.value)}
                required
                disabled={running}
                style={{ fontSize: '0.95rem' }}
              />
            </div>

            <div className="card-header">
              <span className="card-title">🔬 Analysis Domains</span>
            </div>
            <div className="toggle-group mb-4">
              {DOMAINS.map(d => (
                <button
                  key={d}
                  type="button"
                  className={`toggle ${domains[d] ? 'active' : ''}`}
                  onClick={() => setDomains(prev => ({ ...prev, [d]: !prev[d] }))}
                  disabled={running}
                >
                  {DOMAIN_ICONS[d]} {d.replace('_', ' ')}
                </button>
              ))}
            </div>

            <div className="grid-2 mb-4">
              <div className="input-group">
                <label className="input-label">Min Confidence</label>
                <select
                  className="input"
                  value={minConfidence}
                  onChange={e => setMinConfidence(e.target.value)}
                  disabled={running}
                >
                  <option value="HIGH">HIGH only (blocking)</option>
                  <option value="MEDIUM">MEDIUM + HIGH</option>
                  <option value="LOW">All (including LOW)</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">LLM Model</label>
                <select
                  className="input"
                  value={model}
                  onChange={e => setModel(e.target.value)}
                  disabled={running}
                >
                  {MODELS.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="input-group mb-4">
              <label className="input-label">GitHub Token (optional — overrides .env)</label>
              <input
                className="input"
                type="password"
                placeholder="ghp_... (leave empty to use .env token)"
                value={githubToken}
                onChange={e => setGithubToken(e.target.value)}
                disabled={running}
              />
            </div>

            <div className="flex gap-4 mb-6" style={{ alignItems: 'center' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={e => setDryRun(e.target.checked)}
                  disabled={running}
                />
                <span className="text-sm flex items-center gap-2"><Target size={14}/> Dry Run (don't post to GitHub)</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={synthesis}
                  onChange={e => setSynthesis(e.target.checked)}
                  disabled={running}
                />
                <span className="text-sm flex items-center gap-2"><svg className="animate-spin" width="14" height="14" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Cross-file synthesis pass</span>
              </label>
            </div>

            {error && (
              <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '12px 16px', marginBottom: 16, color: '#f87171', fontSize: '0.875rem' }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary btn-lg w-full flex items-center justify-center gap-2"
              disabled={running || !prUrl.trim()}
            >
              {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {running ? 'Reviewing...' : 'Start Review'}
            </button>
          </div>
        </form>

        {/* Live log panel */}
        {running && (
          <div className="animate-in">
            <div className="card" style={{ height: '100%' }}>
              <div className="card-header">
                <span className="card-title flex items-center gap-2">
                  {done ? <><Target size={16} className="text-green-500" /> Review Complete</> : <><Loader2 size={16} className="pulse text-blue-500 animate-spin" /> Live Analysis Log</>}
                </span>
                {runId && (
                  <span className="text-xs font-mono text-muted">{runId.slice(0, 8)}</span>
                )}
              </div>
              <div className="log-console">
                {logs.length === 0 ? (
                  <div className="text-muted">Connecting to agent...</div>
                ) : (
                  logs.map((log, i) => (
                    <div key={i} className={`log-line ${log.level}`}>
                      <span className="ts">{log.ts}</span>
                      <span className="msg" style={{ color: logLevelColor[log.level] }}>
                        {log.message}
                      </span>
                    </div>
                  ))
                )}
                <div ref={logsEndRef} />
              </div>
              {done && runId && (
                <div style={{ marginTop: 16 }}>
                  <button
                    className="btn btn-primary w-full"
                    onClick={() => navigate(`/runs/${runId}`)}
                  >
                    📊 View Full Results
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
