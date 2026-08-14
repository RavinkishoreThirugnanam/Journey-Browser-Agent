import React, { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMemo } from 'react'
import { api } from '../api'
import { Badge, Field, PageHeader } from '../components/Ui'
import { JourneyPage } from './JourneyPage'

export function WorkflowPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const requestedJourneyId = searchParams.get('journey') || ''
  const [form, setForm] = useState({ application_url: 'https://example.com', objective: 'Discover the primary user journey from the application home page.', environment: 'development', project: 'Demo', max_depth: 3, max_pages: 8, follow_links: true, min_events: 10 })
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [configLoading, setConfigLoading] = useState(true)
  const [journeyRefreshKey, setJourneyRefreshKey] = useState(0)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [creationStarted, setCreationStarted] = useState(false)
  const [creationEvents, setCreationEvents] = useState([])
  const [creationStatus, setCreationStatus] = useState('Preparing browser exploration...')
  const [creationError, setCreationError] = useState('')
  const [activeStreamKey, setActiveStreamKey] = useState('')
  const discoveryRef = useRef(null)

  useEffect(() => {
    let mounted = true
    api.getConfiguration().then((config) => {
      if (!mounted) return
      const baseUrl = config?.application?.base_url
      if (baseUrl) {
        setForm((current) => ({ ...current, application_url: baseUrl, environment: config?.application?.environment ?? current.environment, project: config?.application?.default_project ?? current.project, follow_links: config?.application?.default_follow_links !== false }))
      }
    }).catch(() => {}).finally(() => {
      if (mounted) setConfigLoading(false)
    })
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    if (searchParams.get('create') === '1') setShowCreateModal(true)
  }, [searchParams])

  useEffect(() => {
    if (!activeStreamKey) return undefined
    const source = new EventSource(api.liveEventsUrl(activeStreamKey))
    source.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data)
        setCreationEvents((current) => [...current, next].slice(-300))
        if (next.status) setCreationStatus(next.status)
        if (next.type === 'journey_saved' || next.type === 'exploration_failed') source.close()
      } catch {
        // Keep-alive messages do not affect the active run.
      }
    }
    return () => source.close()
  }, [activeStreamKey])

  const closeCreateModal = () => {
    if (loading) return
    setShowCreateModal(false)
    setCreationStarted(false)
    setCreationEvents([])
    setCreationError('')
    setActiveStreamKey('')
  }

  const start = async (e) => {
    e.preventDefault()
    const generatedId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
    const streamKey = `JRN-${generatedId}`
    setLoading(true)
    setMessage('')
    setCreationStarted(true)
    setCreationEvents([])
    setCreationError('')
    setCreationStatus('Preparing objective and connecting to the live browser...')
    setActiveStreamKey(streamKey)
    try {
      const result = await api.startExploration({
        application_url: form.application_url,
        objective: form.objective,
        stream_key: streamKey,
        parameters: { environment: form.environment, project: form.project },
        crawl: { max_depth: Number(form.max_depth), max_pages: Number(form.max_pages), follow_links: form.follow_links, min_events: Number(form.min_events) },
      })
      if (/blocked/i.test(result.outcome || '')) {
        setMessage(`Exploration blocked: ${result.outcome_detail || 'The required objective path was not completed.'}`)
      } else {
        setMessage('Exploration complete. Review the discovered journey below.')
      }
      setJourneyRefreshKey((current) => current + 1)
      if (result.journey_id) navigate(`/journeys/${encodeURIComponent(result.journey_id)}`)
    } catch (error) {
      let detail = error?.message || 'Unknown error'
      try {
        const parsed = JSON.parse(detail)
        detail = parsed.detail || parsed.message || detail
      } catch {
        // Keep the raw API message when the server did not return JSON.
      }
      setCreationError(detail)
      setCreationStatus('Journey creation failed')
      setMessage(`Failed to start exploration: ${detail}`)
    } finally {
      setLoading(false)
    }
  }

  const creationSummary = useMemo(() => {
    const visitedUrls = new Set()
    let reportedPages = 0
    let reportedInteractions = 0
    creationEvents.forEach((event) => {
      if (event.url && ['page_loaded', 'page_scanned', 'navigation_completed'].includes(event.type)) visitedUrls.add(event.url)
      reportedPages = Math.max(reportedPages, Number(event.page_count || 0))
      reportedInteractions = Math.max(reportedInteractions, Number(event.interaction_count || 0))
    })
    const capturedInteractions = creationEvents.filter((event) => ['clicking', 'clicked', 'hovering', 'target_selected', 'replay_event_completed'].includes(event.type)).length
    const latest = creationEvents[creationEvents.length - 1] || null
    const types = new Set(creationEvents.map((event) => event.type))
    const stage = types.has('journey_saved') ? 4
      : types.has('journey_map_building') || types.has('journey_artifacts_ready') ? 3
        : types.has('page_loaded') || types.has('page_scanned') ? 2
          : types.has('execution_plan_compiled') || types.has('status') ? 1 : 0
    return {
      pages: Math.max(visitedUrls.size, reportedPages),
      interactions: Math.max(capturedInteractions, reportedInteractions),
      latest,
      stage,
    }
  }, [creationEvents])

  const creationStages = ['Preparing objective', 'Connecting browser', 'Exploring and capturing', 'Building journey map', 'Ready for review']

  return (
    <>
      <PageHeader
        title="Create Journeys"
        description="Create a new journey or review the browser exploration and evidence from an existing journey."
      />
      {message && <div className="notification-row workflow-page-notification"><Badge tone={/(failed|blocked)/i.test(message) ? 'danger' : 'success'}>{message}</Badge></div>}
      <div ref={discoveryRef} className="workflow-discovery-section workflow-discovery-first">
        <JourneyPage
          refreshKey={journeyRefreshKey}
          initialSelectedId={requestedJourneyId}
          onCreateJourney={() => setShowCreateModal(true)}
        />
      </div>

      {showCreateModal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="create-journey-title">
          <div className="modal-panel journey-create-modal">
            <div className="modal-head">
              <div>
                <h3 id="create-journey-title">{creationStarted ? 'Creating Your Journey Map' : 'Create Journey Maps'}</h3>
                <p>{creationStarted ? 'Watch the browser agent explore, capture interactions, and organize the visited pages into a journey map.' : 'Enter the application details and run browser discovery. The new journey map will appear in Created Journeys.'}</p>
              </div>
              <button type="button" className="secondary-button modal-close-button" onClick={closeCreateModal} disabled={loading}>Close</button>
            </div>
            {configLoading ? (
              <div className="page-loading">Loading configuration...</div>
            ) : creationStarted ? (
              <div className="journey-creation-monitor">
                <div className="journey-creation-status">
                  <div>
                    <span className="journey-live-pulse" aria-hidden="true" />
                    <div><span className="eyebrow">Browser agent activity</span><strong>{creationStatus}</strong></div>
                  </div>
                  <div className="journey-creation-counts">
                    <span><strong>{creationSummary.pages}</strong> pages visited</span>
                    <span><strong>{creationSummary.interactions}</strong> interactions captured</span>
                  </div>
                </div>

                <div className="journey-creation-stages" aria-label="Journey creation progress">
                  {creationStages.map((stage, index) => (
                    <div key={stage} className={index < creationSummary.stage ? 'complete' : index === creationSummary.stage ? 'active' : ''}>
                      <span>{index < creationSummary.stage ? '✓' : index + 1}</span>
                      <small>{stage}</small>
                    </div>
                  ))}
                </div>

                <div className="journey-creation-live-grid">
                  <section className="journey-creation-browser">
                    <div className="journey-monitor-section-head"><strong>Live browser session</strong><small>Read-only agent-controlled preview</small></div>
                    {import.meta.env.VITE_BROWSER_STREAM_URL ? (
                      <iframe title="Live journey creation browser" src={import.meta.env.VITE_BROWSER_STREAM_URL} tabIndex={-1} />
                    ) : (
                      <div className="journey-monitor-unavailable">Browser stream is not configured. Live agent events are still shown.</div>
                    )}
                  </section>
                  <section className="journey-creation-activity">
                    <div className="journey-monitor-section-head"><strong>What the agent is capturing</strong><small>{creationEvents.length} live events</small></div>
                    <div className="journey-creation-current">
                      <span>Current page or target</span>
                      <strong>{creationSummary.latest?.element || creationSummary.latest?.title || creationSummary.latest?.status || 'Waiting for browser activity'}</strong>
                      <small>{creationSummary.latest?.url || form.application_url}</small>
                    </div>
                    <div className="journey-creation-timeline">
                      {creationEvents.slice(-12).reverse().map((event, index) => (
                        <div key={`${event.timestamp || index}-${index}`}>
                          <span className="journey-event-dot" />
                          <p><strong>{event.status || event.type}</strong><small>{event.element || event.result || event.url || ''}</small></p>
                        </div>
                      ))}
                      {!creationEvents.length ? <div className="journey-monitor-waiting">Waiting for the browser agent to start...</div> : null}
                    </div>
                  </section>
                </div>

                <div className={creationError ? 'journey-creation-explanation danger' : 'journey-creation-explanation'}>
                  <strong>{creationError ? 'The journey could not be completed.' : 'How the journey map is created'}</strong>
                  <span>{creationError || 'Visited pages, selected targets, clicks, navigation changes, DOM evidence, and screenshots are being assembled into the journey overview, map, replay, and page-evidence tabs.'}</span>
                </div>
                {creationError ? <div className="modal-footer journey-create-footer"><button type="button" className="secondary-button" onClick={closeCreateModal}>Close</button><button type="button" onClick={() => { setCreationStarted(false); setCreationError(''); setActiveStreamKey('') }}>Try Again</button></div> : null}
              </div>
            ) : (
              <form onSubmit={start} className="form-grid journey-create-form">
                <Field label="Application URL"><input type="url" required value={form.application_url} onChange={(e) => setForm({ ...form, application_url: e.target.value })} /></Field>
                <Field label="Journey Objective"><textarea rows="6" maxLength={6000} required placeholder="Example: Open the base URL, click Preferences, open Workspaces, then inspect Report Lookup." value={form.objective} onChange={(e) => setForm({ ...form, objective: e.target.value })} /></Field>
                <div className="modal-footer journey-create-footer">
                  <button type="button" className="secondary-button" onClick={closeCreateModal} disabled={loading}>Cancel</button>
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





