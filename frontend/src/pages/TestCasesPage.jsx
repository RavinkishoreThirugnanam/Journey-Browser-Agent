import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Badge, Card, Table } from '../components/Ui'
import { useFetch } from '../hooks/useFetch'

function EmptyState({ title, description }) {
  return (
    <div className="empty-card">
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  )
}

export function TestCasesPage() {
  const { data, loading, refetch } = useFetch(api.getTestCases, [])
  const items = data?.items ?? []
  const [journeys, setJourneys] = useState([])
  const [stories, setStories] = useState([])
  const [selectedJourneys, setSelectedJourneys] = useState([])
  const [selectedStories, setSelectedStories] = useState([])
  const [journeyPickerValue, setJourneyPickerValue] = useState('')
  const [message, setMessage] = useState('')
  const [generating, setGenerating] = useState(false)
  const [previewCase, setPreviewCase] = useState(null)

  useEffect(() => {
    api.getJourneys().then((d) => setJourneys(d.items ?? d ?? [])).catch(() => setJourneys([]))
    api.getUserStories().then((d) => setStories(d.items ?? d ?? [])).catch(() => setStories([]))
  }, [])

  const journeyIdOf = (value) => value?.journey_id || value?.source_journey_id || value?.journey?.journey_id || ''
  const storyIdOf = (value) => value?.story_id || value?.user_story_id || value?.story?.story_id || ''

  const selectedJourneySet = useMemo(() => new Set(selectedJourneys), [selectedJourneys])
  const selectedStorySet = useMemo(() => new Set(selectedStories), [selectedStories])
  const selectedJourneyItems = useMemo(() => journeys.filter((journey) => selectedJourneySet.has(journeyIdOf(journey))), [journeys, selectedJourneySet])
  const availableJourneyCount = journeys.filter((journey) => !selectedJourneySet.has(journeyIdOf(journey))).length

  const storiesByJourney = useMemo(() => {
    return stories.reduce((acc, story) => {
      const journeyId = journeyIdOf(story) || 'unknown'
      if (!acc[journeyId]) acc[journeyId] = []
      acc[journeyId].push(story)
      return acc
    }, {})
  }, [stories])

  const selectedJourneyStories = useMemo(() => {
    if (!selectedJourneys.length) return []
    return stories.filter((story) => selectedJourneySet.has(journeyIdOf(story)))
  }, [stories, selectedJourneys, selectedJourneySet])

  const selectedStoryItems = useMemo(() => {
    return stories.filter((story) => selectedStorySet.has(storyIdOf(story)))
  }, [stories, selectedStorySet])

  const journeyScopedTestCases = useMemo(() => {
    if (!selectedJourneys.length) return []
    return items.filter((item) => selectedJourneySet.has(journeyIdOf(item)))
  }, [items, selectedJourneys, selectedJourneySet])

  const visibleTestCases = useMemo(() => {
    if (!selectedStories.length) return journeyScopedTestCases
    return journeyScopedTestCases.filter((item) => selectedStorySet.has(storyIdOf(item)))
  }, [journeyScopedTestCases, selectedStories, selectedStorySet])

  const testCasesByStory = useMemo(() => {
    return visibleTestCases.reduce((acc, item) => {
      const storyId = storyIdOf(item) || 'unknown'
      if (!acc[storyId]) acc[storyId] = []
      acc[storyId].push(item)
      return acc
    }, {})
  }, [visibleTestCases])

  const getJourneyLabel = (journey) => journey?.journey_title || journey?.source_url || journey?.application_url || 'Journey map'
  const getStoryLabel = (story) => story?.summary || story?.title || 'User story'

  const selectAllJourneys = () => {
    setSelectedJourneys(journeys.map((journey) => journey.journey_id))
    setSelectedStories([])
    setJourneyPickerValue('')
  }

  const clearSelection = () => {
    setSelectedJourneys([])
    setSelectedStories([])
    setJourneyPickerValue('')
  }

  const selectAllVisibleStories = () => {
    setSelectedStories(selectedJourneyStories.map((story) => story.story_id))
  }

  const clearStorySelection = () => {
    setSelectedStories([])
  }

  const addJourneyFromDropdown = (event) => {
    const journeyId = event.target.value
    if (!journeyId) return
    if (journeyId === '__all__') {
      selectAllJourneys()
      return
    }
    setSelectedJourneys((current) => (current.includes(journeyId) ? current : [...current, journeyId]))
    setJourneyPickerValue('')
  }

  const removeSelectedJourney = (journeyId) => {
    setSelectedJourneys((current) => current.filter((id) => id !== journeyId))
    setSelectedStories((current) => current.filter((storyId) => {
      const story = stories.find((item) => item.story_id === storyId)
      return story?.journey_id !== journeyId
    }))
  }

  const toggleStory = (storyId) => {
    setSelectedStories((current) => (
      current.includes(storyId)
        ? current.filter((id) => id !== storyId)
        : [...current, storyId]
    ))
  }

  useEffect(() => {
    if (!previewCase) return undefined
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setPreviewCase(null)
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [previewCase])
  const generate = async () => {
    setMessage('')
    if (!selectedJourneys.length) {
      setMessage('Select at least one journey map to load its user stories.')
      return
    }
    if (!selectedStories.length) {
      setMessage('Select the user stories you want to create test cases for.')
      return
    }
    setGenerating(true)
    try {
      const journeyIdsForStories = [...new Set(selectedStoryItems.map((story) => story.journey_id).filter(Boolean))]
      const result = await api.generateTestCases({ journey_ids: journeyIdsForStories, user_story_ids: selectedStories })
      setMessage(`Generated ${result?.count ?? 0} test cases for ${selectedStories.length} selected user stories.`)
      await refetch()
    } catch (error) {
      let detail = error?.message || 'Unable to generate test cases.'
      try { detail = JSON.parse(detail)?.detail || detail } catch {}
      setMessage(detail)
    } finally {
      setGenerating(false)
    }
  }

  const storyJourney = (story) => journeys.find((journey) => journeyIdOf(journey) === journeyIdOf(story))
  const caseStory = (testCase) => stories.find((story) => storyIdOf(story) === storyIdOf(testCase))
  const caseJourney = (testCase) => journeys.find((journey) => journeyIdOf(journey) === journeyIdOf(testCase))
  const journeysWithoutStories = selectedJourneyItems.filter((journey) => !selectedJourneyStories.some((story) => journeyIdOf(story) === journeyIdOf(journey)))

  return (
    <Card
      title="Test Cases"
      subtitle="Choose source stories, generate test cases, and review the results in one place."
      actions={<button onClick={refetch} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>}
    >
      <div className="test-case-minimal-shell">
        <div className="test-case-minimal-toolbar">
          <div className="test-case-minimal-intro">
            <div>
              <span className="eyebrow">Test creation</span>
              <h3>Choose stories and generate cases</h3>
              <p>Add journey context, select the relevant stories, then generate traceable test cases.</p>
            </div>
            <div className="test-case-minimal-counts" aria-label="Current test case selection">
              <span><strong>{selectedJourneys.length}</strong> journeys</span>
              <span><strong>{selectedStories.length}</strong> stories</span>
              <span><strong>{visibleTestCases.length}</strong> cases</span>
            </div>
          </div>

          <div className="test-case-minimal-controls">
            <label className="field test-case-minimal-picker">
              <span>Add journey context</span>
              <select value={journeyPickerValue} onChange={addJourneyFromDropdown} disabled={!journeys.length || !availableJourneyCount}>
                <option value="">{journeys.length ? availableJourneyCount ? 'Choose a journey map' : 'All journey maps selected' : 'No journey maps available'}</option>
                <option value="__all__" disabled={!availableJourneyCount}>Select all journey maps</option>
                {journeys.map((journey) => (
                  <option key={journey.journey_id} value={journey.journey_id} disabled={selectedJourneySet.has(journey.journey_id)}>
                    {getJourneyLabel(journey)}
                  </option>
                ))}
              </select>
            </label>
            <div className="test-case-minimal-control-actions">
              <button type="button" className="secondary-button" onClick={clearSelection} disabled={!selectedJourneys.length && !selectedStories.length}>Clear</button>
            </div>
          </div>

          {selectedJourneyItems.length ? (
            <div className="test-case-minimal-journeys" aria-label="Selected journeys">
              {selectedJourneyItems.map((journey) => (
                <button key={journey.journey_id} type="button" onClick={() => removeSelectedJourney(journey.journey_id)} title="Remove journey">
                  <span>{getJourneyLabel(journey)}</span>
                  <strong aria-hidden="true">×</strong>
                </button>
              ))}
            </div>
          ) : <p className="test-case-minimal-hint">Add a journey map to reveal its generated user stories.</p>}

          {message ? <div className="test-case-minimal-message"><Badge tone={message.includes('Generated') ? 'success' : 'warning'}>{message}</Badge></div> : null}
        </div>

        {selectedJourneys.length ? (
          <div className="test-case-minimal-workspace">
            <div className="test-case-minimal-block">
              <div className="test-case-minimal-heading">
                <div>
                  <h3>User stories</h3>
                  <p>Select only the stories that should produce test cases.</p>
                </div>
                <div className="test-case-minimal-actions">
                  <button type="button" className="secondary-button" onClick={clearStorySelection} disabled={!selectedStories.length}>Clear stories</button>
                </div>
              </div>

              {selectedJourneyStories.length ? (
                <div className="test-case-minimal-story-list">
                  {selectedJourneyStories.map((story) => {
                    const journey = storyJourney(story)
                    return (
                      <label key={storyIdOf(story)} className={`test-case-minimal-story-row ${selectedStorySet.has(storyIdOf(story)) ? 'selected' : ''}`}>
                        <input type="checkbox" checked={selectedStorySet.has(storyIdOf(story))} onChange={() => toggleStory(storyIdOf(story))} />
                        <div className="test-case-minimal-story-copy">
                          <strong>{getStoryLabel(story)}</strong>
                        </div>
                        <div className="test-case-minimal-story-context">
                          <small>{getJourneyLabel(journey)}</small>
                          <Badge tone="neutral">{story.module || 'User Story'}</Badge>
                        </div>
                      </label>
                    )
                  })}
                </div>
              ) : (
                <div className="test-case-minimal-empty">
                  <strong>No user stories are available for the selected journeys.</strong>
                  <span>Generate user stories in Step 2, then return here.</span>
                </div>
              )}

              <div className="test-case-minimal-bottom-actions">
                <button type="button" className="secondary-button" onClick={selectAllVisibleStories} disabled={!selectedJourneyStories.length}>Select all stories</button>
                <button type="button" onClick={generate} disabled={generating || loading || !selectedStories.length}>{generating ? 'Generating...' : 'Generate Test Cases'}</button>
              </div>

              {journeysWithoutStories.length && selectedJourneyStories.length ? (
                <p className="test-case-minimal-note">{journeysWithoutStories.length} selected journey{journeysWithoutStories.length > 1 ? 's have' : ' has'} no generated user stories and {journeysWithoutStories.length > 1 ? 'are' : 'is'} hidden from this list.</p>
              ) : null}
            </div>

            <div className="test-case-minimal-divider" />

            <div className="test-case-minimal-block">
              <div className="test-case-minimal-heading">
                <div>
                  <h3>Generated test cases</h3>
                  <p>{selectedStories.length ? 'Showing cases linked to the selected stories.' : 'Showing all saved cases for the selected journeys.'}</p>
                </div>
                <Badge tone={visibleTestCases.length ? 'success' : 'neutral'}>{visibleTestCases.length} cases</Badge>
              </div>

              {visibleTestCases.length ? (
                <Table
                  columns={['Test Case', 'User Story', 'Journey', 'Type', 'Action']}
                  rows={visibleTestCases.map((item) => {
                    const story = caseStory(item)
                    const journey = caseJourney(item)
                    return (
                      <tr key={item.test_case_id}>
                        <td><strong>{item.title}</strong></td>
                        <td>{getStoryLabel(story)}</td>
                        <td>{getJourneyLabel(journey)}</td>
                        <td><Badge tone="success">{item.test_case_type || 'Functional'}</Badge></td>
                        <td><button type="button" className="secondary-button test-case-preview-trigger" onClick={() => setPreviewCase(item)}>Preview</button></td>
                      </tr>
                    )
                  })}
                />
              ) : (
                <div className="test-case-minimal-empty compact">
                  <strong>No test cases for this selection.</strong>
                  <span>Select user stories above and generate test cases to see them here.</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="test-case-minimal-empty test-case-minimal-start">
            <strong>Select a journey map to begin.</strong>
            <span>User stories and saved test cases will appear in this workspace.</span>
          </div>
        )}
      </div>

      {previewCase && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreviewCase(null) }}>
          <section className="modal-panel test-case-preview-panel" role="dialog" aria-modal="true" aria-labelledby="test-case-preview-title">
            <div className="modal-head">
              <div>
                <span className="eyebrow">Generated Test Case</span>
                <h3 id="test-case-preview-title">{previewCase.title}</h3>
              </div>
              <button type="button" className="secondary-button modal-close-button" onClick={() => setPreviewCase(null)} aria-label="Close test case preview">Close</button>
            </div>
            <div className="test-case-preview-meta">
              <div><span>Type</span><strong>{previewCase.test_case_type || 'Functional'}</strong></div>
              <div><span>Scenario</span><strong>{previewCase.scenario_type || 'Positive'}</strong></div>
              <div><span>Priority</span><strong>{previewCase.priority || 'High'}</strong></div>
              <div><span>Environment</span><strong>{previewCase.environment || 'latest'}</strong></div>
            </div>
            <div className="test-case-preview-section">
              <h4>Purpose &amp; Traceability</h4>
              <p>{previewCase.description || 'No description provided.'}</p>
              <dl className="test-case-preview-definition-list">
                <dt>User story</dt><dd>{previewCase.user_story || '-'}</dd>
                <dt>Journey objective</dt><dd>{previewCase.journey_objective || '-'}</dd>
              </dl>
            </div>
            <div className="test-case-preview-columns">
              <div className="test-case-preview-section">
                <h4>Preconditions</h4>
                {previewCase.preconditions?.length ? <ol className="test-case-preview-list">{previewCase.preconditions.map((item, index) => <li key={`precondition-${index}`}>{item}</li>)}</ol> : <p>-</p>}
              </div>
              <div className="test-case-preview-section">
                <h4>Postconditions</h4>
                {previewCase.postconditions?.length ? <ol className="test-case-preview-list">{previewCase.postconditions.map((item, index) => <li key={`postcondition-${index}`}>{item}</li>)}</ol> : <p>-</p>}
              </div>
            </div>
            <div className="test-case-preview-section">
              <h4>Test Steps</h4>
              {previewCase.steps?.length ? <ol className="test-case-preview-list">{previewCase.steps.map((item, index) => <li key={`step-${index}`}>{item}</li>)}</ol> : <p>-</p>}
            </div>
            <div className="test-case-preview-section">
              <h4>Expected Results</h4>
              {previewCase.expected_results?.length ? <ul className="test-case-preview-list">{previewCase.expected_results.map((item, index) => <li key={`expected-${index}`}>{item}</li>)}</ul> : <p>-</p>}
            </div>
            {previewCase.automation_steps?.length ? (
              <div className="test-case-preview-section">
                <h4>Automation Trace</h4>
                <div className="test-case-preview-automation-list">
                  {previewCase.automation_steps.map((step, index) => (
                    <div key={`automation-${index}`} className="test-case-preview-automation-item">
                      <strong>{index + 1}. {step.action || 'inspect'} — {step.label || 'element'}</strong>
                      <code>{step.selector || 'No selector captured'}</code>
                      {step.destination_url ? <small>{step.destination_url}</small> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      )}
    </Card>
  )
}


