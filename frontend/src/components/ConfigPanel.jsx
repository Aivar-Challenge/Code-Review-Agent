import React, { useEffect, useState } from 'react'
import { getSettings, getSuppressions, createSuppression, deleteSuppression } from '../api'

export default function ConfigPanel() {
  const [settings, setSettings] = useState(null)
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)
  const [newRule, setNewRule] = useState({ repo: '*', file_pattern: '', domain: '*', keyword: '', reason: '' })
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('settings')

  const load = async () => {
    try {
      const [s, r] = await Promise.all([getSettings(), getSuppressions()])
      setSettings(s)
      setRules(r.rules || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await createSuppression(newRule)
      setNewRule({ repo: '*', file_pattern: '', domain: '*', keyword: '', reason: '' })
      load()
    } catch (err) {
      alert(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Deactivate this suppression rule?')) return
    await deleteSuppression(id)
    load()
  }

  if (loading) return <div className="text-muted">Loading...</div>

  return (
    <div className="animate-in">
      <div className="mb-6">
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: 4 }}>Configuration</h2>
        <p className="text-sm text-muted">Agent settings and suppression rules</p>
      </div>

      <div className="tabs">
        {['settings', 'suppressions'].map(t => (
          <div key={t} className={`tab ${activeTab === t ? 'active' : ''}`} onClick={() => setActiveTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
            {t === 'suppressions' && ` (${rules.length})`}
          </div>
        ))}
      </div>

      {activeTab === 'settings' && settings && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="card-header"><span className="card-title">🤖 Agent Configuration</span></div>
            <p className="text-xs text-muted mb-4">These settings come from your .env file. Edit .env to change them.</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                { label: 'LLM Provider', value: settings.llm_provider },
                { label: 'Default Model', value: settings.default_model },
                { label: 'Max Tokens per Chunk', value: settings.max_tokens_per_chunk },
                { label: 'Min Confidence', value: settings.min_confidence },
                { label: 'Dry Run', value: settings.dry_run ? 'Enabled' : 'Disabled' },
              ].map(item => (
                <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                  <span className="text-sm text-muted">{item.label}</span>
                  <span className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>{String(item.value)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-header"><span className="card-title">🔑 API Keys Status</span></div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { label: 'GitHub Token', configured: settings.github_token_configured },
                { label: 'OpenAI API Key', configured: settings.openai_key_configured },
              ].map(item => (
                <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                  <span className="text-sm text-muted">{item.label}</span>
                  <span style={{
                    padding: '2px 10px',
                    borderRadius: 999,
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    background: item.configured ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                    color: item.configured ? '#4ade80' : '#f87171',
                  }}>
                    {item.configured ? '✅ Configured' : '❌ Missing'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'suppressions' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Create new rule */}
          <div className="card">
            <div className="card-header"><span className="card-title">➕ Add Suppression Rule</span></div>
            <p className="text-xs text-muted mb-4">Suppress known false positives from being posted as review comments.</p>
            <form onSubmit={handleCreate}>
              <div className="grid-2 mb-4">
                <div className="input-group">
                  <label className="input-label">Repo ("*" for all)</label>
                  <input className="input" placeholder="owner/repo or *" value={newRule.repo} onChange={e => setNewRule(p => ({ ...p, repo: e.target.value }))} />
                </div>
                <div className="input-group">
                  <label className="input-label">File Pattern (glob)</label>
                  <input className="input" placeholder="tests/* or *.test.js" value={newRule.file_pattern} onChange={e => setNewRule(p => ({ ...p, file_pattern: e.target.value }))} />
                </div>
                <div className="input-group">
                  <label className="input-label">Domain ("*" for all)</label>
                  <select className="input" value={newRule.domain} onChange={e => setNewRule(p => ({ ...p, domain: e.target.value }))}>
                    <option value="*">All domains</option>
                    <option value="correctness">Correctness</option>
                    <option value="security">Security</option>
                    <option value="performance">Performance</option>
                    <option value="test_coverage">Test Coverage</option>
                  </select>
                </div>
                <div className="input-group">
                  <label className="input-label">Keyword (in title/issue)</label>
                  <input className="input" placeholder="e.g. hardcoded" value={newRule.keyword} onChange={e => setNewRule(p => ({ ...p, keyword: e.target.value }))} />
                </div>
              </div>
              <div className="input-group mb-4">
                <label className="input-label">Reason</label>
                <input className="input" placeholder="Why this is suppressed..." value={newRule.reason} onChange={e => setNewRule(p => ({ ...p, reason: e.target.value }))} />
              </div>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Saving...' : '➕ Add Rule'}
              </button>
            </form>
          </div>

          {/* Existing rules */}
          <div className="card">
            <div className="card-header"><span className="card-title">🚫 Active Suppression Rules</span></div>
            {rules.length === 0 ? (
              <div className="empty-state" style={{ padding: '30px 0' }}>
                <div className="icon">✅</div>
                <p>No suppression rules configured</p>
              </div>
            ) : (
              <div className="table-wrapper" style={{ border: 'none' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Repo</th>
                      <th>File Pattern</th>
                      <th>Domain</th>
                      <th>Keyword</th>
                      <th>Reason</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map(rule => (
                      <tr key={rule.id}>
                        <td className="font-mono text-xs">{rule.repo}</td>
                        <td className="font-mono text-xs">{rule.file_pattern || '—'}</td>
                        <td><span className={`badge badge-${rule.domain}`}>{rule.domain}</span></td>
                        <td className="font-mono text-xs">{rule.keyword || '—'}</td>
                        <td className="text-xs text-muted">{rule.reason || '—'}</td>
                        <td>
                          <button className="btn btn-danger btn-sm" onClick={() => handleDelete(rule.id)}>Remove</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
