import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listRuns, deleteRun } from '../api'

const STATUS_OPTS = ['all', 'completed', 'running', 'queued', 'failed']

export default function RunsList() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('all')
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await listRuns(page, 20, status === 'all' ? null : status)
      setRuns(data.runs || [])
      setTotal(data.total || 0)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [page, status])

  const handleDelete = async (e, runId) => {
    e.stopPropagation()
    if (!confirm('Delete this run and all its findings?')) return
    setDeleting(runId)
    try {
      await deleteRun(runId)
      load()
    } finally {
      setDeleting(null)
    }
  }

  const totalPages = Math.ceil(total / 20)

  return (
    <div className="animate-in">
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: 4 }}>All Runs</h2>
          <p className="text-sm text-muted">{total} total runs</p>
        </div>
        <div className="flex gap-2">
          <div className="toggle-group">
            {STATUS_OPTS.map(s => (
              <button key={s} className={`toggle ${status === s ? 'active' : ''}`} onClick={() => { setStatus(s); setPage(1) }}>
                {s}
              </button>
            ))}
          </div>
          <button className="btn btn-primary" onClick={() => navigate('/review/new')}>➕ New</button>
        </div>
      </div>

      <div className="table-wrapper card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>PR</th>
              <th>Repo</th>
              <th>Status</th>
              <th>Findings</th>
              <th>Posted</th>
              <th>Cost</th>
              <th>Started</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>Loading...</td></tr>
            ) : runs.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>No runs found</td></tr>
            ) : (
              runs.map(run => (
                <tr key={run.id} onClick={() => navigate(`/runs/${run.id}`)}>
                  <td>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                      #{run.pr_number}
                    </span>
                    {run.pr_title && (
                      <div className="text-xs text-muted">{run.pr_title.slice(0, 40)}{run.pr_title.length > 40 ? '…' : ''}</div>
                    )}
                  </td>
                  <td className="text-sm">{run.repo || '—'}</td>
                  <td><span className={`badge badge-${run.status}`}>{run.status}</span></td>
                  <td>{run.findings_count ?? '—'}</td>
                  <td style={{ color: run.posted_count > 0 ? '#4ade80' : undefined }}>{run.posted_count ?? '—'}</td>
                  <td className="font-mono text-xs">${(run.estimated_cost_usd || 0).toFixed(4)}</td>
                  <td className="text-xs text-muted">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                  </td>
                  <td>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={(e) => handleDelete(e, run.id)}
                      disabled={deleting === run.id}
                    >
                      {deleting === run.id ? '…' : '🗑️'}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center gap-2 mt-4 justify-between">
          <span className="text-sm text-muted">Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <button className="btn btn-secondary btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <button className="btn btn-secondary btn-sm" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        </div>
      )}
    </div>
  )
}
