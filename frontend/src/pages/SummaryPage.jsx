import React, { useState } from 'react'
import { api } from '../api'
import { Badge, Card, Field } from '../components/Ui'

export function SummaryPage() {
  const [form, setForm] = useState({ output_dir: '' })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const run = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const response = await api.runSummary({ output_dir: form.output_dir || undefined })
      setResult(response)
    } catch (err) {
      setError(err?.message || 'Failed to generate summary.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Step 6 Summary" subtitle="Generate an OpenAI-written markdown summary from the pipeline artifacts.">
      <form onSubmit={run} className="form-grid">
        <Field label="Artifacts Directory" hint="Folder containing the outputs from steps 1 through 5"><input value={form.output_dir} onChange={(e) => setForm({ ...form, output_dir: e.target.value })} placeholder="backend/storage/generated_files" /></Field>
        <button type="submit" disabled={loading}>{loading ? 'Generating...' : 'Run Summary'}</button>
      </form>
      {error ? <div className="notification-row"><Badge tone="danger">{error}</Badge></div> : null}
      {result ? (
        <div className="stack" style={{ marginTop: 20 }}>
          <div className="detail-metadata">
            <div className="detail-row"><span>Output File</span><strong>{result.output_file || '-'}</strong></div>
          </div>
          <div className="panel">
            <h3>Summary Preview</h3>
            <pre className="code-block">{result.report}</pre>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
