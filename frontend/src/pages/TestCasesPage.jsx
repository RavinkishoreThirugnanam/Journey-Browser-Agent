import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
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
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const requestedJourneyId = searchParams.get('journey') || ''
  const requestedJourneyIds = (searchParams.get('journeys') || '').split(',').filter(Boolean)
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

  useEffect(() => {
    if (!journeys.length) return
    const availableIds = new Set(journeys.map((journey) => journey.journey_id))
    const requestedIds = requestedJourneyIds.length ? requestedJourneyIds : (requestedJourneyId ? [requestedJourneyId] : [])
    const validIds = requestedIds.filter((journeyId) => availableIds.has(journeyId))
    if (!validIds.length) return
    setSelectedJourneys(validIds)
    setSelectedStories([])
  }, [journeys, requestedJourneyId, searchParams.get('journeys')])

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

  useEffect(() => {
    setSelectedStories(selectedJourneyStories.map((story) => storyIdOf(story)))
  }, [selectedJourneyStories])

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
  const allJourneysSelected = journeys.length > 1 && selectedJourneys.length === journeys.length
  const journeySelectionValue = allJourneysSelected ? '__all__' : (selectedJourneys.length === 1 ? selectedJourneys[0] : '')
  const selectedJourneyLabel = allJourneysSelected
    ? 'All Journey Maps'
    : (selectedJourneyItems[0] ? getJourneyLabel(selectedJourneyItems[0]) : 'Test Cases')
  const allVisibleStoriesSelected = selectedJourneyStories.length > 0 && selectedJourneyStories.every((story) => selectedStorySet.has(storyIdOf(story)))

  return (
    <Card
      className="test-case-page-flat"
      title="Test Cases"
      subtitle="Select a journey map to review its test cases or generate updated cases."
    >
      <div className="test-case-minimal-shell">
        <div className="test-case-minimal-toolbar">
          <div className="test-case-minimal-controls">
            <label className="field test-case-minimal-picker">
              <span>Journey map</span>
              <select value={journeySelectionValue} onChange={(event) => {
                const journeyId = event.target.value
                setSelectedJourneys(journeyId === '__all__' ? journeys.map((journey) => journey.journey_id) : (journeyId ? [journeyId] : []))
                setSelectedStories([])
              }} disabled={!journeys.length}>
                <option value="">{journeys.length ? 'Select a journey map' : 'No journey maps available'}</option>
                {journeys.length > 1 ? <option value="__all__">Select All Journey Maps</option> : null}
                {journeys.map((journey) => (
                  <option key={journey.journey_id} value={journey.journey_id}>
                    {getJourneyLabel(journey)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {message ? <div className="test-case-minimal-message"><Badge tone={message.includes('Generated') ? 'success' : 'warning'}>{message}</Badge></div> : null}
        </div>

        {selectedJourneys.length ? (
          <div className="test-case-minimal-workspace">
            <div className="test-case-minimal-block">
              <div className="test-case-minimal-heading">
                <div>
                  <h3>Generated test cases</h3>
                  <p>Showing saved cases for the selected journey map.</p>
                </div>
                <div className="test-case-minimal-actions">
                  <Badge tone={visibleTestCases.length ? 'success' : 'neutral'}>{visibleTestCases.length} cases</Badge>
                  {!visibleTestCases.length ? (
                    <button type="button" onClick={generate} disabled={generating || loading || !selectedStories.length}>
                      {generating ? 'Generating...' : 'Generate Test Cases'}
                    </button>
                  ) : null}
                </div>
              </div>

              {!selectedJourneyStories.length ? (
                <div className="test-case-minimal-empty compact">
                  <strong>No user stories are available for this journey.</strong>
                  <span>Generate user stories in Stage 2 before creating test cases.</span>
                </div>
              ) : visibleTestCases.length ? (
                <Table
                  columns={['Test Case', 'User Story', 'Journey', 'Action']}
                  rows={visibleTestCases.map((item) => {
                    const story = caseStory(item)
                    const journey = caseJourney(item)
                    return (
                      <tr key={item.test_case_id}>
                        <td><strong>{item.title}</strong></td>
                        <td>{getStoryLabel(story)}</td>
                        <td>{getJourneyLabel(journey)}</td>
                        <td><button type="button" className="secondary-button test-case-preview-trigger" onClick={() => setPreviewCase(item)}>Preview</button></td>
                      </tr>
                    )
                  })}
                />
              ) : (
                <div className="test-case-minimal-empty compact">
                  <strong>No test cases generated yet.</strong>
                  <span>Generate test cases from the selected journey&apos;s user stories.</span>
                </div>
              )}

              {journeysWithoutStories.length && selectedJourneyStories.length ? (
                <p className="test-case-minimal-note">{journeysWithoutStories.length} selected journey{journeysWithoutStories.length > 1 ? 's have' : ' has'} no generated user stories.</p>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="test-case-minimal-empty test-case-minimal-start">
            <strong>Select a journey map to begin.</strong>
            <span>User stories and saved test cases will appear in this workspace.</span>
          </div>
        )}
      </div>

      <footer className="workflow-fixed-footer test-cases-fixed-footer">
        <div className="workflow-fixed-stage"><strong>Stage 3 of 5</strong><span>&bull;</span><span>{selectedJourneyLabel}</span></div>
        <div className="workflow-fixed-actions">
          <button type="button" className="secondary-button" onClick={() => navigate(selectedJourneys.length === 1 ? `/stories?journey=${encodeURIComponent(selectedJourneys[0])}` : '/stories')}>Back to User Stories</button>
          <button type="button" onClick={() => navigate(selectedJourneys.length === 1 ? `/scripts?journey=${encodeURIComponent(selectedJourneys[0])}` : `/scripts?journeys=${encodeURIComponent(selectedJourneys.join(','))}`)} disabled={!visibleTestCases.length}>Continue to Test Scripts <span aria-hidden="true">&rarr;</span></button>
        </div>
      </footer>

      {previewCase && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreviewCase(null) }}>
          <section className="modal-panel test-case-preview-panel test-case-preview-simple" role="dialog" aria-modal="true" aria-labelledby="test-case-preview-title">
            <div className="test-case-preview-simple-body">
              <h3 id="test-case-preview-title">{previewCase.title}</h3>
              <p className="test-case-preview-purpose">{previewCase.description || 'Why this test case exists'}</p>
              <p className="test-case-preview-origin"><strong>Comes from:</strong> “{previewCase.user_story || getStoryLabel(caseStory(previewCase)) || 'Generated user story'}”</p>
              <div className="test-case-preview-steps">
                <span>Steps</span>
                {previewCase.steps?.length ? (
                  <ol>{previewCase.steps.map((item, index) => <li key={`step-${index}`}>{item}</li>)}</ol>
                ) : <p>No generated steps are available.</p>}
              </div>
            </div>
            <footer className="test-case-preview-simple-footer">
              <button type="button" onClick={() => setPreviewCase(null)}>Close</button>
            </footer>
          </section>
        </div>
      )}
    </Card>
  )
}


