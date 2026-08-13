import React, { useState } from 'react'
import { api } from '../api'
import { ActionBar, Badge, Card } from '../components/Ui'

const filenames = {
  journeys: 'journeys.json',
  'user-stories': 'user_stories.json',
  'test-cases': 'test_cases.json',
  'test-scripts': 'test_scripts.json',
}

const labels = {
  journeys: 'Journeys',
  'user-stories': 'User Stories',
  'test-cases': 'Test Cases',
  'test-scripts': 'Test Scripts',
}

function displayDate(value) {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function JourneyReview({ item, index }) {
  return (
    <article className="export-review-card">
      <div className="export-review-head">
        <div>
          <span className="export-review-eyebrow">Journey {index + 1}</span>
          <h4>{item.title}</h4>
          {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">{item.source_url}</a>}
        </div>
        <Badge tone={String(item.outcome).toLowerCase().includes('complete') ? 'success' : 'neutral'}>{item.outcome}</Badge>
      </div>
      <div className="export-review-metrics">
        <div><span>Steps</span><strong>{item.step_count ?? 0}</strong></div>
        <div><span>Events</span><strong>{item.event_count ?? 0}</strong></div>
        <div><span>Pages</span><strong>{item.page_count ?? 0}</strong></div>
        <div><span>Captured</span><strong>{displayDate(item.captured_at)}</strong></div>
      </div>
      {item.objective && (
        <div className="export-review-copy">
          <strong>Journey objective</strong>
          <p>{item.objective}</p>
        </div>
      )}
      {item.steps?.length > 0 && (
        <details className="export-review-details">
          <summary>View captured pages and steps ({item.steps.length})</summary>
          <ol>
            {item.steps.map((step, stepIndex) => (
              <li key={`${item.id}-step-${step.number ?? stepIndex}`}>
                <div>
                  <strong>{step.title || `Step ${stepIndex + 1}`}</strong>
                  {step.url && <span>{step.url}</span>}
                </div>
                <small>{step.action || 'Observed'} · {step.interaction_count ?? 0} interactions</small>
              </li>
            ))}
          </ol>
        </details>
      )}
    </article>
  )
}

function StoryReview({ item, index }) {
  return (
    <article className="export-review-card">
      <div className="export-review-head">
        <div>
          <span className="export-review-eyebrow">User Story {index + 1}</span>
          <h4>{item.title}</h4>
          {item.module && <span className="export-review-subtitle">{item.module}</span>}
        </div>
        <Badge tone="neutral">{item.status}</Badge>
      </div>
      {item.description && <p className="export-review-description">{item.description}</p>}
      {item.acceptance_criteria?.length > 0 && (
        <details className="export-review-details">
          <summary>Acceptance criteria ({item.acceptance_criteria.length})</summary>
          <ul>
            {item.acceptance_criteria.map((criterion, criterionIndex) => (
              <li key={`${item.id}-criterion-${criterionIndex}`}>{criterion.ac_text || String(criterion)}</li>
            ))}
          </ul>
        </details>
      )}
    </article>
  )
}

function TestCaseReview({ item, index }) {
  return (
    <article className="export-review-card">
      <div className="export-review-head">
        <div>
          <span className="export-review-eyebrow">Test Case {index + 1}</span>
          <h4>{item.title}</h4>
        </div>
        <div className="export-review-badges">
          {item.priority && <Badge tone="neutral">{item.priority}</Badge>}
          <Badge tone="neutral">{item.type}</Badge>
        </div>
      </div>
      {item.description && <p className="export-review-description">{item.description}</p>}
      <div className="export-review-metrics export-review-metrics-compact">
        <div><span>Steps</span><strong>{item.steps?.length ?? 0}</strong></div>
        <div><span>Evidence</span><strong>{item.evidence_count ?? 0}</strong></div>
      </div>
      {item.steps?.length > 0 && (
        <details className="export-review-details">
          <summary>View test procedure</summary>
          <ol>{item.steps.map((step, stepIndex) => <li key={`${item.id}-test-step-${stepIndex}`}>{String(step)}</li>)}</ol>
        </details>
      )}
    </article>
  )
}

function ScriptReview({ item, index }) {
  return (
    <article className="export-review-card">
      <div className="export-review-head">
        <div>
          <span className="export-review-eyebrow">Test Script {index + 1}</span>
          <h4>{item.title}</h4>
        </div>
        <Badge tone="neutral">{item.evidence_count ?? 0} evidence</Badge>
      </div>
      {item.objective && <p className="export-review-description">{item.objective}</p>}
      <div className="export-file-list">
        <div><span>Gherkin</span><strong>{item.feature_filename || 'Not generated'}</strong></div>
        <div><span>JavaScript</span><strong>{item.javascript_filename || 'Not generated'}</strong></div>
      </div>
    </article>
  )
}

function ReviewRecord({ artifactType, item, index }) {
  if (artifactType === 'journeys') return <JourneyReview item={item} index={index} />
  if (artifactType === 'user-stories') return <StoryReview item={item} index={index} />
  if (artifactType === 'test-cases') return <TestCaseReview item={item} index={index} />
  return <ScriptReview item={item} index={index} />
}

function limitedText(value, limit = 1800) {
  const text = value == null ? '' : String(value)
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

function normalizeJourney(item, metadata = {}) {
  const hints = item?.test_hints || {}
  const rawSteps = Array.isArray(item?.steps) ? item.steps : []
  const eventLog = Array.isArray(item?.event_log) ? item.event_log : Array.isArray(item?.events) ? item.events : []
  const eventIds = Array.isArray(hints.event_ids) ? hints.event_ids : []
  const pageIds = Array.isArray(hints.page_ids) ? hints.page_ids : []
  return {
    id: item?.id || item?.journey_id || metadata.exploration_id || '',
    title: limitedText(item?.title || item?.journey_title || item?.starting_point || metadata.starting_feature || 'Untitled journey', 240),
    source_url: limitedText(item?.source_url || item?.starting_url || metadata.app_url || '', 600),
    outcome: limitedText(item?.outcome || 'Captured', 100),
    captured_at: item?.captured_at || metadata.exploration_timestamp || item?.created_at || '',
    objective: limitedText(item?.objective || hints.journey_objective || metadata.task_input || ''),
    depth: item?.depth ?? item?.total_depth ?? metadata.depth_level ?? 0,
    step_count: item?.step_count ?? rawSteps.length,
    event_count: item?.event_count ?? (eventLog.length || eventIds.length),
    page_count: item?.page_count ?? new Set(pageIds).size,
    steps: rawSteps.slice(0, 15).map((step, index) => ({
      number: step?.number ?? step?.step_number ?? index + 1,
      title: limitedText(step?.title || step?.page_title || step?.description || `Step ${index + 1}`, 300),
      url: limitedText(step?.url || step?.page_url || step?.source_url || '', 600),
      action: limitedText(step?.action || step?.event || 'Observed', 120),
      interaction_count: step?.interaction_count ?? (Array.isArray(step?.interactions) ? step.interactions.length : 0),
    })),
  }
}

function normalizeExportPreview(artifactType, payload) {
  const rawItems = Array.isArray(payload?.items) ? payload.items : []
  let items = []

  if (artifactType === 'journeys') {
    items = rawItems.flatMap((bundle) => {
      const metadata = bundle?.exploration_metadata || {}
      return Array.isArray(bundle?.journeys)
        ? bundle.journeys.map((journey) => normalizeJourney(journey, metadata))
        : [normalizeJourney(bundle, metadata)]
    })
  } else if (artifactType === 'user-stories') {
    items = rawItems.map((item) => ({
      id: item?.id || item?.story_id || '',
      journey_id: item?.journey_id || '',
      title: limitedText(item?.title || item?.summary || 'Untitled user story', 300),
      module: limitedText(item?.module || item?.epic || '', 160),
      description: limitedText(item?.description || ''),
      acceptance_criteria: (Array.isArray(item?.acceptance_criteria) ? item.acceptance_criteria : []).slice(0, 20).map((criterion) => ({
        ac_text: limitedText(criterion?.ac_text || criterion, 800),
      })),
      status: limitedText(item?.status || item?.jira_sync_status || 'Local', 80),
    }))
  } else if (artifactType === 'test-cases') {
    items = rawItems.map((item) => ({
      id: item?.id || item?.test_case_id || '',
      journey_id: item?.journey_id || '',
      title: limitedText(item?.title || 'Untitled test case', 300),
      description: limitedText(item?.description || ''),
      priority: limitedText(item?.priority || '', 80),
      type: limitedText(item?.type || item?.test_case_type || item?.scenario_type || 'Functional', 100),
      preconditions: (Array.isArray(item?.preconditions) ? item.preconditions : []).slice(0, 15).map((value) => limitedText(value, 600)),
      steps: (Array.isArray(item?.steps) ? item.steps : []).slice(0, 25).map((value) => limitedText(value, 800)),
      expected_results: (Array.isArray(item?.expected_results) ? item.expected_results : []).slice(0, 25).map((value) => limitedText(value, 800)),
      evidence_count: item?.evidence_count ?? (Array.isArray(item?.source_evidence) ? item.source_evidence.length : 0),
    }))
  } else {
    items = rawItems.map((item) => ({
      id: item?.id || item?.script_id || '',
      test_case_id: item?.test_case_id || '',
      title: limitedText(item?.title || item?.feature_filename || item?.javascript_filename || 'Generated test script', 300),
      feature_filename: limitedText(item?.feature_filename || '', 300),
      javascript_filename: limitedText(item?.javascript_filename || '', 300),
      objective: limitedText(item?.objective || item?.journey_objective || ''),
      evidence_count: item?.evidence_count ?? item?.source_evidence_count ?? 0,
      generated_at: item?.generated_at || '',
    }))
  }

  return { artifact_type: artifactType, count: items.length, preview: true, items }
}
export function ExportPage() {
  const [artifactType, setArtifactType] = useState('journeys')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [visibleCount, setVisibleCount] = useState(10)
  const [showTechnical, setShowTechnical] = useState(false)

  const selectArtifact = (event) => {
    setArtifactType(event.target.value)
    setData(null)
    setError('')
    setVisibleCount(10)
    setShowTechnical(false)
  }

  const exportArtifact = async () => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 30000)
    setLoading(true)
    setData(null)
    setError('')
    setShowTechnical(false)
    try {
      const payload = await api.exportArtifact(artifactType, { signal: controller.signal, cache: 'no-store' })
      setData(normalizeExportPreview(artifactType, payload))
    } catch (requestError) {
      setError(requestError?.name === 'AbortError'
        ? 'The preview took too long. Please try again or download the JSON directly.'
        : requestError?.message || 'The preview could not be loaded.')
    } finally {
      window.clearTimeout(timeout)
      setLoading(false)
    }
  }

  const items = Array.isArray(data?.items) ? data.items : []
  const visibleItems = items.slice(0, visibleCount)
  const technicalSample = data ? JSON.stringify({
    artifact_type: data.artifact_type,
    total_records: items.length,
    note: 'Technical preview is limited to three lightweight records. Download the file for the complete payload.',
    items: items.slice(0, 3),
  }, null, 2) : ''

  return (
    <Card title="Review & Export" subtitle="Review generated artifacts in a readable format, then download the complete JSON when needed.">
      <div className="export-toolbar panel" style={{ marginTop: 18 }}>
        <div className="field">
          <span>What would you like to review?</span>
          <select className="journey-select" value={artifactType} onChange={selectArtifact}>
            <option value="journeys">Journeys</option>
            <option value="user-stories">User Stories</option>
            <option value="test-cases">Test Cases</option>
            <option value="test-scripts">Test Scripts</option>
          </select>
        </div>
        <ActionBar>
          <button onClick={exportArtifact} disabled={loading}>{loading ? 'Loading preview...' : `Preview ${labels[artifactType]}`}</button>
          <button className="secondary-button" onClick={() => api.downloadArtifact(artifactType)}>Download {filenames[artifactType]}</button>
        </ActionBar>
      </div>

      {error && <div className="export-error" role="alert">{error}</div>}

      {data && (
        <section className="export-review-section">
          <div className="export-review-title">
            <div>
              <span className="eyebrow">Review results</span>
              <h3>{labels[artifactType]}</h3>
              <p>{items.length} {items.length === 1 ? 'record' : 'records'} ready to review.</p>
            </div>
            <Badge tone="neutral">{items.length} total</Badge>
          </div>

          {items.length === 0 ? (
            <div className="page-evidence-empty-state">
              <strong>No {labels[artifactType].toLowerCase()} available</strong>
              <span>Complete the related workflow step before exporting this artifact.</span>
            </div>
          ) : (
            <div className="export-review-list">
              {visibleItems.map((item, index) => (
                <ReviewRecord key={item.id || `${artifactType}-${index}`} artifactType={artifactType} item={item} index={index} />
              ))}
            </div>
          )}

          {visibleCount < items.length && (
            <button className="secondary-button export-load-more" onClick={() => setVisibleCount((count) => count + 10)}>
              Show 10 more
            </button>
          )}

          {items.length > 0 && (
            <details className="export-technical-preview" open={showTechnical} onToggle={(event) => setShowTechnical(event.currentTarget.open)}>
              <summary>Technical JSON sample</summary>
              {showTechnical && <pre className="code-block">{technicalSample}</pre>}
            </details>
          )}
        </section>
      )}
    </Card>
  )
}