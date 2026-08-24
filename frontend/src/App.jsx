import { useState, useEffect } from 'react'
import DisagreementsTable from './components/DisagreementsTable'
import { fetchDisagreements } from './api/client'
import './App.css'

export default function App() {
  const [disagreements, setDisagreements] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reasonFilter, setReasonFilter] = useState('')
  const [orgFilter, setOrgFilter] = useState('')
  const [ordering, setOrdering] = useState('record_id')

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchDisagreements({ reason: reasonFilter, org_id: orgFilter, ordering })
      .then(data => {
        setDisagreements(data)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [reasonFilter, orgFilter, ordering])

  return (
    <div className="app">
      <h1>System Reconciliation</h1>
      <p className="subtitle">Records where System A and System B disagree.</p>

      <div className="filters">
        <label>
          Reason{' '}
          <select value={reasonFilter} onChange={e => setReasonFilter(e.target.value)}>
            <option value="">All</option>
            <option value="MISSING_IN_B">Missing in B</option>
            <option value="ORPHAN_IN_B">Orphan in B</option>
            <option value="DUPLICATE_IN_B">Duplicate in B</option>
            <option value="VALUE_MISMATCH">Value Mismatch</option>
            <option value="LOCATION_MISMATCH">Location Mismatch</option>
          </select>
        </label>

        <label>
          Organization{' '}
          <select value={orgFilter} onChange={e => setOrgFilter(e.target.value)}>
            <option value="">All</option>
            <option value="ORG-A">ORG-A</option>
            <option value="ORG-B">ORG-B</option>
          </select>
        </label>

        <label>
          Sort by{' '}
          <select value={ordering} onChange={e => setOrdering(e.target.value)}>
            <option value="record_id">Record ID</option>
            <option value="system_a_value">System A Value ↑</option>
            <option value="-system_a_value">System A Value ↓</option>
            <option value="system_b_value">System B Value ↑</option>
            <option value="-system_b_value">System B Value ↓</option>
          </select>
        </label>
      </div>

      {loading && <p className="state">Loading...</p>}
      {error && <p className="state error">Error: {error}</p>}
      {!loading && !error && disagreements.length === 0 && (
        <p className="state">No disagreements found.</p>
      )}
      {!loading && !error && disagreements.length > 0 && (
        <DisagreementsTable rows={disagreements} />
      )}
    </div>
  )
}
