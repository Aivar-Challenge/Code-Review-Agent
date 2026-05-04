import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getStats, listRuns } from '../api'

const DOMAIN_COLORS = {
  correctness: '#ef4444',
  security: '#f97316',
  performance: '#eab308',
  test_coverage: '#22c55e',
}

function StatCard({ label, value, sub, icon, accent }) {
  return (
    <div className="stat-card" style={accent ? { borderColor: `${accent}30` } : {}}>
      <div className="stat-label">{icon} {label}</div>
      <div className="stat-value" style={accent ? { color: accent } : {}}>{value ?? '—'}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [recentRuns, setRecentRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const load = async () => {
    try {
      const [s, r] = await Promise.all([getStats(), listRuns(1, 5)])
      setStats(s)
      setRecentRuns(r.runs || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 10000) // auto-refresh every 10s
    return () => clearInterval(interval)
  }, [])

  if (loading) return (
    <div className="animate-in">
      <div className="stats-grid">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="stat-card">
            <div className="skeleton" style={{ height: 12, width: '60%', marginBottom: 8 }} />
            <div className="skeleton" style={{ height: 36, width: '40%' }} />
          </div>
        ))}
      </div>
    </div>
  )

  const maxDomain = stats ? Math.max(...Object.values(stats.domain_breakdown || {}), 1) : 1

  return (
    <div className="animate-in">
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: 4 }}>Dashboard</h2>
          <p className="text-sm text-muted">Overview of all code review activity</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/review/new')}>
          ➕ New Review
        </button>
      </div>

      {/* Stats grid */}
      <div className="stats-grid">
        <StatCard icon="🔄" label="Total Runs" value={stats?.total_runs} sub={`${stats?.completed_runs} completed`} />
        <StatCard icon="🐛" label="Total Findings" value={stats?.total_findings} sub={`${stats?.posted_findings} posted to GitHub`} accent="#3b82f6" />
        <StatCard icon="🔴" label="Correctness" value={stats?.domain_breakdown?.correctness} accent="#ef4444" />
        <StatCard icon="🔐" label="Security" value={stats?.domain_breakdown?.security} accent="#f97316" />
        <StatCard icon="💰" label="Total Cost" value={`$${(stats?.total_cost_usd || 0).toFixed(4)}`} sub={`${(stats?.total_tokens || 0).toLocaleString()} tokens`} />
      </div>

      <div className="grid-2">
        {/* Domain breakdown */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Findings by Domain</span>
          </div>
          {Object.entries(stats?.domain_breakdown || {}).map(([domain, count]) => (
            <div className="domain-bar" key={domain}>
              <span className="domain-name">{domain.replace('_', ' ')}</span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{
                    width: `${(count / maxDomain) * 100}%`,
                    background: DOMAIN_COLORS[domain] || '#3b82f6',
                  }}
                />
              </div>
              <span className="domain-count">{count}</span>
            </div>
          ))}
          {!stats?.domain_breakdown && <p className="text-muted text-sm">No data yet</p>}
        </div>

        {/* Quick actions */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Quick Actions</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <button className="btn btn-primary w-full" onClick={() => navigate('/review/new')}>
              🔍 Start a New Review
            </button>
            <button className="btn btn-secondary w-full" onClick={() => navigate('/runs')}>
              📋 View All Runs
            </button>
            <button className="btn btn-secondary w-full" onClick={() => navigate('/config')}>
              ⚙️ Configure Agent
            </button>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary w-full"
            >
              📖 API Documentation
            </a>
          </div>
        </div>
      </div>

      {/* Recent runs */}
      <div className="card mt-4">
        <div className="card-header">
          <span className="card-title">Recent Runs</span>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/runs')}>View all</button>
        </div>
        {recentRuns.length === 0 ? (
          <div className="empty-state">
            <div className="icon">🤖</div>
            <h3>No runs yet</h3>
            <p>Start your first code review to see results here</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>PR</th>
                  <th>Status</th>
                  <th>Findings</th>
                  <th>Posted</th>
                  <th>Cost</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map(run => (
                  <tr key={run.id} onClick={() => navigate(`/runs/${run.id}`)}>
                    <td>
                      <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                        #{run.pr_number} {run.repo}
                      </div>
                      <div className="text-xs text-muted">{run.pr_title?.slice(0, 50)}</div>
                    </td>
                    <td><span className={`badge badge-${run.status}`}>{run.status}</span></td>
                    <td>{run.findings_count ?? '—'}</td>
                    <td>{run.posted_count ?? '—'}</td>
                    <td className="font-mono text-xs">${(run.estimated_cost_usd || 0).toFixed(4)}</td>
                    <td className="text-xs text-muted">
                      {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
