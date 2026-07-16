import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { Badge, Card, Table } from '../components/Ui'
import { renderMermaid } from '../utils/mermaid'

function DetailRow({ label, value }) {
  return (
    <div className="detail-row">
      <span>{label}</span>
      <strong>{value || '-'}</strong>
    </div>
  )
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return String(value)
  if (typeof value === 'object') return JSON.stringify(value)
  return value
}

const detailTabs = [
  { id: 'journey-detail', label: 'Journey Details' },
  { id: 'visualization', label: 'Journey Visualization' },
  { id: 'enrichment', label: 'Payload & UI Elements' },
  { id: 'flow-details', label: 'Steps & Interactions' },
]

export function JourneyPage({ refreshKey = 0, initialSelectedId = '' } = {}) {
  const [data, setData] = useState([])
  const [selected, setSelected] = useState('')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [vizJourneyId, setVizJourneyId] = useState('')
  const [mermaidText, setMermaidText] = useState('')
  const [svg, setSvg] = useState('')
  const [vizLoading, setVizLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('journey-detail')
  const detailRef = useRef(null)

  const load = async () => {
    setLoading(true)
    try {
      const response = await api.getJourneys()
      setData(response.items ?? response ?? [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [refreshKey])

  useEffect(() => {
    if (!selected) return
    setVizJourneyId(selected)
  }, [selected])

  useEffect(() => {
    if (!detail || activeTab !== 'visualization' || !selected) return
    if (vizJourneyId === selected && (mermaidText || svg)) return
    generateVisualization({ preventDefault: () => {} })
  }, [activeTab, detail, selected, vizJourneyId])

  useEffect(() => {
    if (initialSelectedId) setSelected(initialSelectedId)
  }, [initialSelectedId])

  useEffect(() => {
    if (!selected) {
      setDetail(null)
      return
    }
    api.getJourney(selected).then((result) => {
      setDetail(result)
      setActiveTab('journey-detail')
      requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    }).catch(() => setDetail(null))
  }, [selected])

  const generateVisualization = async (e) => {
    e?.preventDefault?.()
    if (!vizJourneyId) {
      setMessage('Select a journey to visualize.')
      return
    }
    setVizLoading(true)
    setMessage('')
    setSvg('')
    try {
      const result = await api.visualizeJourney({ journey_id: vizJourneyId })
      setMermaidText(result.mermaid)
      const svgMarkup = await renderMermaid(`journey-viz-${Date.now()}`, result.mermaid)
      setSvg(svgMarkup)
      setActiveTab('visualization')
      setMessage('Journey visualization generated.')
      requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    } catch {
      setMessage('Unable to generate the visual representation.')
    } finally {
      setVizLoading(false)
    }
  }

  const handleRowDelete = async (journeyId) => {
    setMessage('')
    const confirmed = window.confirm('Delete this journey discovery? This cannot be undone.')
    if (!confirmed) return
    try {
      await api.deleteJourney(journeyId)
      if (selected === journeyId) {
        setSelected('')
        setDetail(null)
      }
      await load()
      setMessage('Journey deleted successfully.')
    } catch {
      setMessage('Unable to delete the selected journey.')
    }
  }

  const deleteJourneys = async () => {
    setMessage('')
    const confirmed = window.confirm('Delete all journey discoveries? This cannot be undone.')
    if (!confirmed) return
    try {
      await api.resetJourneys()
      setSelected('')
      setDetail(null)
      await load()
      setMessage('Journey discoveries deleted successfully.')
    } catch {
      setMessage('Unable to delete journey discoveries.')
    }
  }

  const steps = detail?.steps ?? []
  const metadata = detail?.exploration_metadata ?? detail?.explorationMetadata ?? {
    app_url: detail?.app_url ?? detail?.starting_url ?? detail?.source_url ?? '',
    starting_feature: detail?.starting_feature ?? detail?.starting_point ?? '',
    task_input: detail?.task_input ?? '',
    browser: detail?.browser ?? 'chromium',
    viewport: detail?.viewport ?? {},
    is_pre_login_scoped: detail?.is_pre_login_scoped ?? false,
    total_journeys_discovered: detail?.total_journeys_discovered ?? 0,
    exploration_timestamp: detail?.exploration_timestamp ?? '',
  }

  const uiElements = detail?.page_url_ui_element_section?.ui_elements_data ?? detail?.ui_elements_data ?? []
  const browserJourneys = detail?.browser_agent_section?.browser_agent_data?.journeys ?? []
  const selectedJourney = data.find((item) => item.journey_id === selected) || null

  const rows = data.map((j) => (
    <tr key={j.journey_id} onClick={() => setSelected(j.journey_id)} className={selected === j.journey_id ? 'row-selected' : ''}>
      <td><input type="radio" name="journey" checked={selected === j.journey_id} onChange={() => setSelected(j.journey_id)} /></td>
      <td>{j.journey_id}</td>
      <td>{j.application_url}</td>
      <td>{j.starting_url ?? j.application_url}</td>
      <td><Badge tone="info">{j.steps?.length ?? 0} steps</Badge></td>
      <td><Badge tone="neutral">{j.events?.length ?? 0} events</Badge></td>
      <td>
        <button
          className="secondary-button icon-button danger-button"
          title="Delete journey"
          aria-label="Delete journey"
          onClick={(e) => {
            e.stopPropagation()
            handleRowDelete(j.journey_id)
          }}
          disabled={loading}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M7 7h10M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7m-7 0 .7 11.2A1.8 1.8 0 0 0 10.5 20h3a1.8 1.8 0 0 0 1.8-1.8L16 7M10 11v5m4-5v5" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          </svg>
        </button>
      </td>
    </tr>
  ))

  const renderActiveTab = () => {
    if (!detail) {
      return null
    }

    if (activeTab === 'journey-detail') {
      const startingUrl = detail.starting_url || selectedJourney?.starting_url || selectedJourney?.application_url
      const applicationUrl = detail.application_url || selectedJourney?.application_url || metadata.app_url
      const sourceUrl = detail.source_url || selectedJourney?.source_url || selectedJourney?.application_url
      const viewport = metadata.viewport?.width ? `${metadata.viewport.width} x ${metadata.viewport.height}` : formatValue(metadata.viewport)
      const outcomeTone = String(detail.outcome || '').toLowerCase().includes('complete') ? 'success' : 'info'

      return (
        <section className="journey-report journey-report-compact">
          <div className="journey-report-header">
            <div>
              <p className="journey-report-kicker">Journey Details</p>
              <h2>{detail.journey_title || selectedJourney?.journey_title || 'Selected Journey'}</h2>
              <p>{detail.summary || detail.reasoning || `${steps.length} steps captured from ${startingUrl || 'the selected application'}.`}</p>
            </div>
            <Badge tone={outcomeTone}>{detail.outcome || 'Discovered'}</Badge>
          </div>

          <div className="journey-report-meta">
            <div>
              <span>Journey ID</span>
              <strong>{formatValue(detail.journey_id || selected)}</strong>
            </div>
            <div>
              <span>Steps</span>
              <strong>{steps.length}</strong>
            </div>
            <div>
              <span>Events</span>
              <strong>{detail.events?.length ?? selectedJourney?.events?.length ?? 0}</strong>
            </div>
            <div>
              <span>Browser</span>
              <strong>{formatValue(metadata.browser)}</strong>
            </div>
          </div>

          <div className="journey-markdown-grid">
            <div className="journey-report-section">
              <h3>Starting Context</h3>
              <p><strong>Starting point:</strong> {formatValue(detail.starting_point || metadata.starting_feature)}</p>
              <p><strong>Starting URL:</strong> {formatValue(startingUrl)}</p>
              <p><strong>Application URL:</strong> {formatValue(applicationUrl)}</p>
              <p><strong>Source URL:</strong> {formatValue(sourceUrl)}</p>
            </div>

            <div className="journey-report-section">
              <h3>Exploration Metadata</h3>
              <ul>
                <li><strong>Task input:</strong> {formatValue(metadata.task_input)}</li>
                <li><strong>Viewport:</strong> {viewport}</li>
                <li><strong>Captured:</strong> {formatValue(metadata.exploration_timestamp)}</li>
                <li><strong>Pre-login scoped:</strong> {formatValue(metadata.is_pre_login_scoped)}</li>
                <li><strong>Journeys discovered:</strong> {formatValue(metadata.total_journeys_discovered)}</li>
              </ul>
            </div>
          </div>

          <div className="journey-report-section">
            <h3>Outcome Notes</h3>
            <p>{detail.outcome_detail || detail.reasoning || 'No additional outcome notes were captured for this journey.'}</p>
          </div>

          <div className="journey-report-section">
            <h3>Discovery Summary</h3>
            <ul>
              <li><strong>Total depth:</strong> {formatValue(detail.total_depth)}</li>
              <li><strong>Session boundary reached:</strong> {formatValue(detail.session_boundary_reached ?? false)}</li>
              <li><strong>UI enrichment pages:</strong> {uiElements.length}</li>
            </ul>
          </div>
        </section>
      )
    }

    if (activeTab === 'visualization') {
      return (
        <section className="card journey-visualization-card">
          <div className="journey-visualization-header">
            <div>
              <p className="journey-report-kicker">Flowchart</p>
              <h2>Journey Visualization</h2>
              <p>Auto-generated from the selected journey map.</p>
            </div>
            <button className="secondary-button" onClick={() => api.downloadMermaid(vizJourneyId || selected)} disabled={!(vizJourneyId || selected)}>Download `mermaid` file</button>
          </div>
          {vizLoading && <div className="empty-state journey-viz-loading">Generating visual representation...</div>}
          {svg ? (
            <div className="mermaid-panel journey-mermaid-canvas" dangerouslySetInnerHTML={{ __html: svg }} />
          ) : (
            <div className="empty-state journey-viz-loading">Open this tab after selecting a journey to generate the flowchart.</div>
          )}
        </section>
      )
    }

    if (activeTab === 'enrichment') {
      const combinedStatus = detail.browser_agent_section ? 'Combined payload available' : 'Legacy journey payload'

      return (
        <section className="journey-report journey-report-compact">
          <div className="journey-report-header">
            <div>
              <p className="journey-report-kicker">Step 1.5 Enrichment</p>
              <h2>Payload & UI Elements</h2>
              <p>Browser-agent output and DOM/UI element enrichment are combined here so downstream story, test-case, and script generation have the same source context.</p>
            </div>
            <Badge tone={detail.browser_agent_section ? 'success' : 'warning'}>{combinedStatus}</Badge>
          </div>

          <div className="journey-report-meta">
            <div>
              <span>Browser Journeys</span>
              <strong>{browserJourneys.length}</strong>
            </div>
            <div>
              <span>UI Pages</span>
              <strong>{uiElements.length}</strong>
            </div>
            <div>
              <span>Payload Type</span>
              <strong>{detail.browser_agent_section ? 'Nested' : 'Legacy'}</strong>
            </div>
            <div>
              <span>Selected Journey</span>
              <strong>{formatValue(selectedJourney?.journey_id || selected)}</strong>
            </div>
          </div>

          <div className="journey-markdown-grid">
            <div className="journey-report-section">
              <h3>Payload Sections</h3>
              <ul>
                <li><strong>Browser agent section:</strong> {detail.browser_agent_section ? 'Available' : 'Not available'}</li>
                <li><strong>Page URL UI element section:</strong> {uiElements.length ? 'Available' : 'No UI pages captured'}</li>
                <li><strong>Selected journey:</strong> {formatValue(selectedJourney?.journey_title || selectedJourney?.journey_id || selected)}</li>
              </ul>
            </div>

            <div className="journey-report-section">
              <h3>Enrichment Coverage</h3>
              <ul>
                <li><strong>Total UI pages:</strong> {uiElements.length}</li>
                <li><strong>Total extracted elements:</strong> {uiElements.reduce((total, page) => total + (page.extracted_url_ui_elements?.page?.total_elements ?? page.extracted_url_ui_elements?.page?.elements?.length ?? 0), 0)}</li>
                <li><strong>Login-context pages:</strong> {uiElements.filter((page) => page.is_login_flow_context).length}</li>
              </ul>
            </div>
          </div>

          <div className="journey-report-section journey-report-table-section">
            <h3>Journey UI Elements</h3>
            {uiElements.length ? (
              <Table
                columns={['Page URL', 'Source File', 'Login Context', 'Elements']}
                rows={uiElements.map((page) => (
                  <tr key={page.page_url}>
                    <td>{page.page_url}</td>
                    <td>{page.source_file || '-'}</td>
                    <td>{String(page.is_login_flow_context)}</td>
                    <td>{page.extracted_url_ui_elements?.page?.total_elements ?? page.extracted_url_ui_elements?.page?.elements?.length ?? 0}</td>
                  </tr>
                ))}
              />
            ) : (
              <p>No UI enrichment pages were captured for this journey.</p>
            )}
          </div>
        </section>
      )
    }

    if (activeTab === 'flow-details') {
      return (
        <section className="journey-report journey-report-compact">
          <div className="journey-report-header">
            <div>
              <p className="journey-report-kicker">Journey Flow</p>
              <h2>Steps & Interactions</h2>
              <p>Ordered journey steps and the detailed UI interactions captured inside each step are shown together for traceability.</p>
            </div>
            <Badge tone={steps.length ? 'success' : 'neutral'}>{steps.length} steps</Badge>
          </div>

          <div className="journey-report-meta">
            <div>
              <span>Total Steps</span>
              <strong>{steps.length}</strong>
            </div>
            <div>
              <span>Total Interactions</span>
              <strong>{steps.reduce((total, step) => total + (step.interactions?.length ?? 0), 0)}</strong>
            </div>
            <div>
              <span>Events</span>
              <strong>{detail.events?.length ?? selectedJourney?.events?.length ?? 0}</strong>
            </div>
            <div>
              <span>Depth</span>
              <strong>{formatValue(detail.total_depth)}</strong>
            </div>
          </div>

          <div className="journey-report-section journey-report-table-section">
            <h3>Extracted Steps</h3>
            {steps.length ? (
              <Table columns={['Step', 'Depth', 'Page', 'Interactions']} rows={steps.map((step) => (
                <tr key={`${step.step_number}-${step.page_url}`}>
                  <td>{step.step_number}</td>
                  <td>{step.depth_level}</td>
                  <td>
                    <div>{step.page_title}</div>
                    <small>{step.page_url}</small>
                  </td>
                  <td>{step.interactions?.length ?? 0}</td>
                </tr>
              ))} />
            ) : (
              <p>No extracted steps were captured for this journey.</p>
            )}
          </div>

          <div className="journey-report-section journey-report-table-section">
            <h3>Step Interactions</h3>
            {steps.some((step) => step.interactions?.length) ? (
              <div className="journey-interaction-stack">
                {steps.map((step) => (
                  <section key={`step-detail-${step.step_number}`} className="journey-report-page">
                    <h4>Step {step.step_number}: {step.page_title || 'Untitled page'}</h4>
                    {(step.interactions ?? []).length ? (
                      <Table
                        columns={['Sequence', 'Element', 'Action', 'Result', 'Selector']}
                        rows={(step.interactions ?? []).map((interaction, index) => (
                          <tr key={`${step.step_number}-${interaction.sequence_id ?? index}`}>
                            <td>{interaction.sequence_id ?? index + 1}</td>
                            <td>
                              <div>{interaction.element_type}</div>
                              <small>{interaction.element_label}</small>
                            </td>
                            <td>{interaction.action}</td>
                            <td>
                              <div>{interaction.resulted_in}</div>
                              {interaction.validation_message ? <small>{interaction.validation_message}</small> : null}
                            </td>
                            <td>
                              <div>{interaction.selector}</div>
                              <small>{interaction.selector_type}</small>
                            </td>
                          </tr>
                        ))}
                      />
                    ) : (
                      <p>No interactions were captured for this step.</p>
                    )}
                  </section>
                ))}
              </div>
            ) : (
              <p>No detailed step interactions were captured for this journey.</p>
            )}
          </div>
        </section>
      )
    }

    return null
  }

  return (
    <Card
      title="Created Journeys"
      subtitle="Select a created journey map to inspect details, visualization, payload, UI elements, steps, and interactions."
      actions={<><button onClick={load} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button><button className="secondary-button" onClick={deleteJourneys} disabled={loading}>Delete Journey Discovery</button></>}
    >
      <Table columns={['Select', 'Journey ID', 'Application URL', 'Source URL', 'Steps', 'Events', 'Action']} rows={rows} />
      <div className="inline-actions">
        {message && <div className="notification-row"><Badge tone={message.includes('deleted') ? 'danger' : 'warning'}>{message}</Badge></div>}
      </div>

      {detail && (
        <div ref={detailRef} className="detail-tabs-shell">
          <div className="detail-tabs">
            {detailTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`detail-tab ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="detail-tab-panel">
            {renderActiveTab()}
          </div>
        </div>
      )}
    </Card>
  )
}
