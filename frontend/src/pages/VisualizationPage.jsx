import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { ActionBar, Badge, Card, Field } from '../components/Ui'
import { renderMermaid } from '../utils/mermaid'

export function VisualizationPage() {
  const [journeyId, setJourneyId] = useState('')
  const [journeyOptions, setJourneyOptions] = useState([])
  const [mermaidText, setMermaidText] = useState('')
  const [svg, setSvg] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.getJourneys().then((d) => setJourneyOptions(d.items ?? d ?? [])).catch(() => {})
  }, [])

  useEffect(() => {
    if (!mermaidText) return
    let cancelled = false
    ;(async () => {
      try {
        const svgMarkup = await renderMermaid(`mermaid-${Date.now()}`, mermaidText)
        if (!cancelled) setSvg(svgMarkup)
      } catch {
        if (!cancelled) setMessage('Unable to render Mermaid diagram.')
      }
    })()
    return () => { cancelled = true }
  }, [mermaidText])

  const generate = async (e) => {
    e.preventDefault()
    setLoading(true)
    setMessage('')
    setSvg('')
    try {
      const result = await api.visualizeJourney({ journey_id: journeyId })
      setMermaidText(result.mermaid)
      setMessage('Mermaid diagram generated.')
    } catch {
      setMessage('Select a valid journey ID to visualize.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Journey Visualization" subtitle="Convert journey steps into Mermaid and inspect the flowchart interactively.">
      <form className="form-inline" onSubmit={generate}>
        <Field label="Journey">
          <select className="journey-select" value={journeyId} onChange={(e) => setJourneyId(e.target.value)}>
            <option value="">Select a journey</option>
            {journeyOptions.map((j) => (
              <option key={j.journey_id} value={j.journey_id}>{j.journey_id}</option>
            ))}
          </select>
        </Field>
        <button type="submit" disabled={loading}>{loading ? 'Generating...' : 'Generate Visual Representation'}</button>
      </form>
      <ActionBar>
        <button onClick={() => api.downloadMermaid(journeyId)} disabled={!journeyId}>Download `mermaid` file</button>
      </ActionBar>
      {message && <div className="notification-row"><Badge tone={message.includes('generated') ? 'success' : 'warning'}>{message}</Badge></div>}
      {svg && <div className="mermaid-panel" dangerouslySetInnerHTML={{ __html: svg }} />}
      {mermaidText && <pre className="code-block">{mermaidText}</pre>}
    </Card>
  )
}
