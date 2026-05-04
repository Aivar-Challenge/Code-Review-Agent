const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function startReview(prUrl, config = {}) {
  const res = await fetch(`${API}/api/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pr_url: prUrl, config }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getRun(runId) {
  const res = await fetch(`${API}/api/review/${runId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function listRuns(page = 1, limit = 20, status = null) {
  const params = new URLSearchParams({ page, limit })
  if (status) params.set('status', status)
  const res = await fetch(`${API}/api/runs?${params}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteRun(runId) {
  const res = await fetch(`${API}/api/runs/${runId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getStats() {
  const res = await fetch(`${API}/api/runs/stats/summary`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getSettings() {
  const res = await fetch(`${API}/api/config/settings`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getSuppressions() {
  const res = await fetch(`${API}/api/config/suppressions`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createSuppression(rule) {
  const res = await fetch(`${API}/api/config/suppressions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rule),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteSuppression(ruleId) {
  const res = await fetch(`${API}/api/config/suppressions/${ruleId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export function connectLogsWebSocket(runId, onMessage, onDone) {
  const wsUrl = (API.replace('http', 'ws')) + `/ws/logs/${runId}`
  const ws = new WebSocket(wsUrl)

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.message === '__DONE__') {
        onDone?.()
      } else if (data.message !== '__PING__') {
        onMessage(data)
      }
    } catch {}
  }

  ws.onerror = (e) => console.error('WS error', e)
  return ws
}
