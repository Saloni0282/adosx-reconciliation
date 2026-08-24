export default function DisagreementsTable({ rows }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Record</th>
          <th>Org</th>
          <th>Reason</th>
          <th>System A Value</th>
          <th>System B Value</th>
          <th>Location(s)</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(row => (
          <tr key={row.id}>
            <td><code>{row.record_id}</code></td>
            <td>{row.reason === 'LOCATION_MISMATCH' ? `${row.org_id || '?'} / ${row.system_b_org_id || '?'}` : (row.org_id || row.system_b_org_id || '—')}</td>
            <td><span className={`reason reason-${row.reason}`}>{row.reason}</span></td>
            <td>{row.system_a_value ?? <em>—</em>}</td>
            <td>{
              row.reason === 'DUPLICATE_IN_B' ? <em>Duplicate entries: {row.system_b_entry_ids.join(', ')}</em> :
              (row.system_b_value !== null ? row.system_b_value : (row.system_b_raw_value ? <em>raw: {row.system_b_raw_value}</em> : <em>—</em>))
            }</td>
            <td>{row.reason === 'LOCATION_MISMATCH' ? `A: ${row.system_a_location} / B: ${row.system_b_location}` : (row.system_a_location || row.system_b_location || '—')}</td>
            <td className="notes">{row.notes}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
