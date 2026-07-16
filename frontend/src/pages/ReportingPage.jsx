import React, { useState } from 'react'
import { api } from '../api'
import { Badge, Card, Field } from '../components/Ui'

export function ReportingPage() {
  const [form, setForm] = useState({ report_path: '', output_dir: '', push_to_jira: false })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const run = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const payload = {
        report_path: form.report_path,
        output_dir: form.output_dir || undefined,
        push_to_jira: form.push_to_jira,
      }
      const response = await api.runReporting(payload)
      setResult(response)
    } catch (err) {
      setError(err?.message || 'Failed to run reporting pipeline.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Step 5 Reporting" subtitle="Parse test reports and optionally create Jira bugs for failed scenarios.">
      <form onSubmit={run} className="form-grid">
        <Field label="Report Path" hint="Cucumber JSON file or directory containing JSON reports"><input value={form.report_path} onChange={(e) => setForm({ ...form, report_path: e.target.value })} placeholder="backend/storage/reports" /></Field>
        <Field label="Output Directory" hint="Optional folder for saved Jira payloads"><input value={form.output_dir} onChange={(e) => setForm({ ...form, output_dir: e.target.value })} placeholder="backend/storage/generated_files/reporting" /></Field>
        <label className="field checkbox-field checkbox-clickable">
          <span>Push Failed Scenarios to Jira</span>
          <input type="checkbox" checked={form.push_to_jira} onChange={(e) => setForm({ ...form, push_to_jira: e.target.checked })} />
        </label>
        <button type="submit" disabled={loading}>{loading ? 'Processing...' : 'Run Reporting Pipeline'}</button>
      </form>
      {error ? <div className="notification-row"><Badge tone="danger">{error}</Badge></div> : null}
      {result ? (
        <div className="stack" style={{ marginTop: 20 }}>
          <div className="detail-metadata">
            <div className="detail-row"><span>Payloads</span><strong>{result.count}</strong></div>
            <div className="detail-row"><span>Saved Path</span><strong>{result.saved_path || '-'}</strong></div>
            <div className="detail-row"><span>Jira Results</span><strong>{result.jira_results?.length ?? 0}</strong></div>
          </div>
          {Array.isArray(result.jira_results) && result.jira_results.length ? (
            <div className="panel">
              <h3>Jira Sync Results</h3>
              <div className="stack">
                {result.jira_results.map((item, index) => (
                  <div key={`${item.dedup_key || index}`} className="detail-row">
                    <span>{item.summary}</span>
                    <strong>{item.sync_status === 'synced' ? item.jira_key : item.error || 'local only'}</strong>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  )
}
