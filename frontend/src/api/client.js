const API_BASE = 'http://localhost:8000/api'

export async function fetchDisagreements({ reason = '', org_id = '', ordering = 'record_id' } = {}) {
  const params = new URLSearchParams()
  if (reason) params.set('reason', reason)
  if (org_id) params.set('org_id', org_id)
  if (ordering) params.set('ordering', ordering)

  const url = `${API_BASE}/disagreements/?${params.toString()}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`)
  return res.json()
}
