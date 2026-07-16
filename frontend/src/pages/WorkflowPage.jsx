import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Badge, Field, PageHeader } from '../components/Ui'
import { JourneyPage } from './JourneyPage'

export function WorkflowPage() {
  const [form, setForm] = useState({ application_url: 'https://example.com', environment: 'development', project: 'Demo', max_depth: 1, max_pages: 8, follow_links: true })
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [configLoading, setConfigLoading] = useState(true)
  const [journeyRefreshKey, setJourneyRefreshKey] = useState(0)
  const [latestJourneyId, setLatestJourneyId] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const discoveryRef = useRef(null)

  useEffect(() => {
    let mounted = true
    api.getConfiguration().then((config) => {
      if (!mounted) return
      const baseUrl = config?.application?.base_url
      if (baseUrl) {
        setForm((current) => ({ ...current, application_url: baseUrl, environment: config?.application?.environment ?? current.environment, project: config?.application?.default_project ?? current.project }))
      }
    }).catch(() => {}).finally(() => {
      if (mounted) setConfigLoading(false)
    })
    return () => { mounted = false }
  }, [])

  const start = async (e) => {
    e.preventDefault()
    setLoading(true)
    setMessage('')
    try {
      const result = await api.startExploration({
        application_url: form.application_url,
        parameters: { environment: form.environment, project: form.project },
        crawl: { max_depth: Number(form.max_depth), max_pages: Number(form.max_pages), follow_links: form.follow_links },
      })
      setMessage(`Exploration complete: ${result.journey_id}. Review the discovered journey below.`)
      setLatestJourneyId(result.journey_id || '')
      setJourneyRefreshKey((current) => current + 1)
      setShowCreateModal(false)
      requestAnimationFrame(() => {
        discoveryRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    } catch {
      setMessage('Failed to start exploration.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Workflow"
        title="Explore & Discover Journey"
        description="Review created journey maps first, then create new journey maps from a target application URL when needed."
        actions={<button type="button" onClick={() => setShowCreateModal(true)}>Create New Journey</button>}
      />
      {message && <div className="notification-row workflow-page-notification"><Badge tone={message.includes('Failed') ? 'danger' : 'success'}>{message}</Badge></div>}
      <div ref={discoveryRef} className="workflow-discovery-section workflow-discovery-first">
        <JourneyPage refreshKey={journeyRefreshKey} initialSelectedId={latestJourneyId} />
      </div>

      {showCreateModal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="create-journey-title">
          <div className="modal-panel journey-create-modal">
            <div className="modal-head">
              <div>
                <h3 id="create-journey-title">Create Journey Maps</h3>
                <p>Enter the application details and run browser discovery. The new journey map will appear in Created Journeys.</p>
              </div>
              <button type="button" className="secondary-button modal-close-button" onClick={() => setShowCreateModal(false)} disabled={loading}>Close</button>
            </div>
            {configLoading ? (
              <div className="page-loading">Loading configuration...</div>
            ) : (
              <form onSubmit={start} className="form-grid journey-create-form">
                <Field label="Application URL"><input value={form.application_url} onChange={(e) => setForm({ ...form, application_url: e.target.value })} /></Field>
                <Field label="Environment"><input value={form.environment} onChange={(e) => setForm({ ...form, environment: e.target.value })} /></Field>
                <Field label="Default Project"><input value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })} /></Field>
                <Field label="Max Depth"><input type="number" min="0" value={form.max_depth} onChange={(e) => setForm({ ...form, max_depth: e.target.value })} /></Field>
                <Field label="Max Pages"><input type="number" min="1" value={form.max_pages} onChange={(e) => setForm({ ...form, max_pages: e.target.value })} /></Field>
                <label className="field checkbox-field checkbox-clickable journey-follow-links-field">
                  <span>
                    Follow Links
                    <small>Allow the browser agent to follow discovered same-site links during exploration.</small>
                  </span>
                  <input type="checkbox" checked={form.follow_links} onChange={(e) => setForm({ ...form, follow_links: e.target.checked })} />
                </label>
                <div className="modal-footer journey-create-footer">
                  <button type="button" className="secondary-button" onClick={() => setShowCreateModal(false)} disabled={loading}>Cancel</button>
                  <button type="submit" disabled={loading}>{loading ? 'Creating Journey Maps...' : 'Create Journey Maps'}</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  )
}
