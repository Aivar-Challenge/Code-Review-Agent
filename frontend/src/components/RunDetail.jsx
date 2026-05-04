import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getRun, connectLogsWebSocket } from '../api'

const DOMAIN_COLORS = {
  correctness: { bg: 'rgba(239,68,68,0.1)', text: '#f87171', border: 'rgba(239,68,68,0.3)', icon: '🐛' },
  security: { bg: 'rgba(249,115,22,0.1)', text: '#fb923c', border: 'rgba(249,115,22,0.3)', icon: '🔐' },
  performance: { bg: 'rgba(234,179,8,0.1)', text: '#fbbf24', border: 'rgba(234,179,8,0.3)', icon: '⚡' },
  test_coverage: { bg: 'rgba(34,197,94,0.1)', text: '#4ade80', border: 'rgba(34,197,94,0.3)', icon: '🧪' },
}

const CONF_COLORS = { HIGH: '#ef4444', MEDIUM: '#f59e0b', LOW: '#6b7280' }

function FindingCard({ finding, expanded, onToggle }) {
  const dc = DOMAIN_COLORS[finding.domain] || {}
  const confColor = CONF_COLORS[finding.confidence] || '#94a3b8'

  return (
    <div
      className="finding-card"
      style={{ borderColor: finding.suppressed ? 'transparent' : undefined, opacity: finding.suppressed ? 0.5 : 1 }}
    >
      <div className="finding-header" onClick={onToggle} style={{ cursor: 'pointer' }}>
        <span style={{
          background: dc.bg,
          color: dc.text,
          border: `1px solid ${dc.border}`,
          borderRadius: 999,
          padding: '2px 10px',
          fontSize: '0.72rem',
          fontWeight: 600,
          flexShrink: 0,
        }}>
          {dc.icon} {finding.domain?.replace('_', ' ')}
        </span>
        <span style={{
          background: `${confColor}18`,
          color: confColor,
          border: `1px solid ${confColor}40`,
          borderRadius: 999,
          padding: '2px 10px',
          fontSize: '0.72rem',
          fontWeight: 700,
          flexShrink: 0,
        }}>
          {finding.confidence}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="finding-title">{finding.title}</div>
          <div className="finding-meta">
            {finding.file_path}
            {finding.line_number ? `:${finding.line_number}` : ''}
            {finding.suppressed ? ' · skipped' : finding.posted ? ' · ✅ posted' : ''}
          </div>
        </div>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <div style={{ marginTop: 12, borderTop: '1px solid var(--border-subtle)', paddingTop: 12 }}>
          <div className="finding-body">
            <p style={{ marginBottom: 8 }}><strong style={{ color: 'var(--text-primary)' }}>Issue:</strong> {finding.issue}</p>
            <p style={{ marginBottom: 8 }}><strong style={{ color: 'var(--text-primary)' }}>Impact:</strong> {finding.why_it_matters}</p>
          </div>
          {finding.fix_suggestion && (
            <div className="finding-fix">
              <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-accent)', marginBottom: 6 }}>✅ Suggested Fix</div>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{finding.fix_suggestion}</p>
            </div>
          )}
          {finding.code_example && (
            <div className="code-example">{finding.code_example}</div>
          )}
        </div>
      )}
    </div>
  )
}

export default function RunDetail() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const [run, setRun] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('findings')
  const [expandedId, setExpandedId] = useState(null)
  const [filterDomain, setFilterDomain] = useState('all')
  const [filterConf, setFilterConf] = useState('all')
  const [filterStatus, setFilterStatus] = useState('all')
  const [logs, setLogs] = useState([])
  const logsEndRef = React.useRef(null)

  const load = async () => {
    try {
      const data = await getRun(runId)
      setRun(data)
      setLogs(data.logs || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [runId])

  // Auto-refresh if run is still going
  useEffect(() => {
    if (!run || run.status === 'completed' || run.status === 'failed') return
    const ws = connectLogsWebSocket(
      runId,
      (entry) => setLogs(prev => [...prev, { ...entry, ts: new Date().toLocaleTimeString() }]),
      () => load(),
    )
    return () => ws.close()
  }, [run?.status])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  if (loading) return <div className="text-muted">Loading...</div>
  if (!run) return <div className="text-muted">Run not found.</div>

  const findings = run.findings || []
  const filtered = findings.filter(f => {
    if (filterDomain !== 'all' && f.domain !== filterDomain) return false
    if (filterConf !== 'all' && f.confidence !== filterConf) return false
    if (filterStatus === 'posted' && !f.posted) return false
    if (filterStatus === 'suppressed' && !f.suppressed) return false
    if (filterStatus === 'active' && (f.posted || f.suppressed)) return false
    return true
  })

  // Stats
  const byDomain = {}
  for (const f of findings) byDomain[f.domain] = (byDomain[f.domain] || 0) + 1

  const logLevelColor = {
    info: 'var(--text-secondary)', success: '#4ade80',
    warning: '#fbbf24', error: '#f87171', debug: 'var(--text-muted)',
  }

  return (
    <div className="animate-in">
      {/* Back + header */}
      <div className="mb-4 flex items-center gap-4">
        <button className="btn btn-secondary btn-sm" onClick={() => navigate('/runs')}>← Back</button>
        <div>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700 }}>
            #{run.pr_number} {run.repo}
          </h2>
          <p className="text-xs text-muted font-mono">{run.commit_sha?.slice(0, 8)} · by @{run.pr_author}</p>
        </div>
        <span className={`badge badge-${run.status}`} style={{ marginLeft: 'auto' }}>
          {run.status === 'running' && <span className="pulse">🟢 </span>}
          {run.status}
        </span>
      </div>

      {/* Quick stats */}
      <div className="stats-grid mb-6">
        <div className="stat-card">
          <div className="stat-label">Total Findings</div>
          <div className="stat-value">{run.findings_count ?? findings.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Posted</div>
          <div className="stat-value" style={{ color: '#4ade80' }}>{run.posted_count ?? 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Suppressed</div>
          <div className="stat-value" style={{ color: '#6b7280' }}>{run.suppressed_count ?? 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Cost</div>
          <div className="stat-value" style={{ fontSize: '1.4rem' }}>
            ${(run.cost?.estimated_cost_usd || 0).toFixed(4)}
          </div>
          <div className="stat-sub">{(run.cost?.total_tokens || 0).toLocaleString()} tokens</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {['findings', 'logs', 'cost', 'config'].map(t => (
          <div key={t} className={`tab ${activeTab === t ? 'active' : ''}`} onClick={() => setActiveTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
            {t === 'findings' && ` (${findings.length})`}
            {t === 'logs' && ` (${logs.length})`}
          </div>
        ))}
      </div>

      {/* Findings tab */}
      {activeTab === 'findings' && (
        <div>
          {/* Filters */}
          <div className="flex gap-2 mb-4 flex-wrap">
            <select className="input" style={{ width: 'auto' }} value={filterDomain} onChange={e => setFilterDomain(e.target.value)}>
              <option value="all">All Domains</option>
              <option value="correctness">🐛 Correctness</option>
              <option value="security">🔐 Security</option>
              <option value="performance">⚡ Performance</option>
              <option value="test_coverage">🧪 Test Coverage</option>
            </select>
            <select className="input" style={{ width: 'auto' }} value={filterConf} onChange={e => setFilterConf(e.target.value)}>
              <option value="all">All Confidence</option>
              <option value="HIGH">🔴 HIGH</option>
              <option value="MEDIUM">🟡 MEDIUM</option>
              <option value="LOW">⬜ LOW</option>
            </select>
            <select className="input" style={{ width: 'auto' }} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
              <option value="all">All Status</option>
              <option value="posted">✅ Posted</option>
              <option value="suppressed">🚫 Suppressed</option>
              <option value="active">⚡ Active</option>
            </select>
            <span className="text-xs text-muted" style={{ alignSelf: 'center', marginLeft: 8 }}>
              {filtered.length} of {findings.length} shown
            </span>
          </div>

          {filtered.length === 0 ? (
            <div className="empty-state">
              <div className="icon">✅</div>
              <h3>No findings match filters</h3>
              <p>Try adjusting your filters or this PR is clean!</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {filtered.map(f => (
                <FindingCard
                  key={f.id}
                  finding={f}
                  expanded={expandedId === f.id}
                  onToggle={() => setExpandedId(expandedId === f.id ? null : f.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Logs tab */}
      {activeTab === 'logs' && (
        <div className="log-console" style={{ maxHeight: 600 }}>
          {logs.length === 0 ? (
            <span className="text-muted">No logs available.</span>
          ) : (
            logs.map((log, i) => (
              <div key={i} className={`log-line ${log.level || 'info'}`}>
                <span className="ts">{log.ts || ''}</span>
                <span className="msg" style={{ color: logLevelColor[log.level] || 'var(--text-secondary)' }}>
                  {log.message}
                </span>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      )}

      {/* Cost tab */}
      {activeTab === 'cost' && (
        <div className="card">
          <div className="card-header"><span className="card-title">💰 Token Usage & Cost Report</span></div>
          <div className="grid-2">
            <div>
              <div className="stat-card mb-4">
                <div className="stat-label">Total Tokens</div>
                <div className="stat-value">{(run.cost?.total_tokens || 0).toLocaleString()}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Estimated Cost</div>
                <div className="stat-value" style={{ fontSize: '1.6rem' }}>
                  ${(run.cost?.estimated_cost_usd || 0).toFixed(4)}
                </div>
              </div>
            </div>
            <div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {[
                  { label: 'Prompt Tokens', value: run.cost?.prompt_tokens, color: '#3b82f6' },
                  { label: 'Completion Tokens', value: run.cost?.completion_tokens, color: '#10b981' },
                ].map(item => (
                  <div key={item.label}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: '0.8rem' }}>
                      <span className="text-muted">{item.label}</span>
                      <span style={{ fontWeight: 600 }}>{(item.value || 0).toLocaleString()}</span>
                    </div>
                    <div className="progress-bar">
                      <div
                        className="fill"
                        style={{
                          width: `${((item.value || 0) / Math.max(run.cost?.total_tokens || 1, 1)) * 100}%`,
                          background: item.color,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 text-xs text-muted">
                Model: <span className="font-mono">{run.config?.model || 'gpt-4o-mini'}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Config tab */}
      {activeTab === 'config' && (
        <div className="card">
          <div className="card-header"><span className="card-title">⚙️ Run Configuration</span></div>
          <pre className="code-example" style={{ whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(run.config, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
