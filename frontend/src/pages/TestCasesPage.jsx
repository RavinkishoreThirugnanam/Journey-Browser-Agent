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
  const [generationMeta, setGenerationMeta] = useState({ jira_synced_count: 0, jira_failed_count: 0 })
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    api.getJourneys().then((d) => setJourneys(d.items ?? d ?? [])).catch(() => setJourneys([]))
    api.getUserStories().then((d) => setStories(d.items ?? d ?? [])).catch(() => setStories([]))
  }, [])

  const selectedJourneySet = useMemo(() => new Set(selectedJourneys), [selectedJourneys])
  const selectedStorySet = useMemo(() => new Set(selectedStories), [selectedStories])
  const selectedJourneyItems = useMemo(() => journeys.filter((journey) => selectedJourneySet.has(journey.journey_id)), [journeys, selectedJourneySet])
  const availableJourneyCount = journeys.filter((journey) => !selectedJourneySet.has(journey.journey_id)).length

  const storiesByJourney = useMemo(() => {
    return stories.reduce((acc, story) => {
      const journeyId = story.journey_id || 'unknown'
      if (!acc[journeyId]) acc[journeyId] = []
      acc[journeyId].push(story)
      return acc
    }, {})
  }, [stories])

  const selectedJourneyStories = useMemo(() => {
    if (!selectedJourneys.length) return []
    return stories.filter((story) => selectedJourneySet.has(story.journey_id))
  }, [stories, selectedJourneys, selectedJourneySet])

  const selectedStoryItems = useMemo(() => {
    return stories.filter((story) => selectedStorySet.has(story.story_id))
  }, [stories, selectedStorySet])

  const visibleTestCases = useMemo(() => {
    if (!selectedStories.length) return []
    return items.filter((item) => selectedStorySet.has(item.user_story_id))
  }, [items, selectedStories, selectedStorySet])

  const testCasesByStory = useMemo(() => {
    return visibleTestCases.reduce((acc, item) => {
      const storyId = item.user_story_id || 'unknown'
      if (!acc[storyId]) acc[storyId] = []
      acc[storyId].push(item)
      return acc
    }, {})
  }, [visibleTestCases])

  const getJourneyLabel = (journey) => journey?.journey_title || journey?.source_url || journey?.application_url || journey?.journey_id || 'Journey map'
  const getStoryLabel = (story) => story?.summary || story?.title || story?.story_id || 'User story'

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
      setGenerationMeta({
        jira_synced_count: result?.jira_synced_count ?? 0,
        jira_failed_count: result?.jira_failed_count ?? 0,
      })
      setMessage(`Generated ${result?.count ?? 0} test cases for ${selectedStories.length} selected user stories.`)
      await refetch()
    } catch {
      setMessage('Unable to generate test cases.')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Card
      title="Test Cases"
      subtitle="Generate structured test cases for selected user stories. Journey maps are used as context only."
      actions={<button onClick={refetch} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>}
    >
      <div className="story-command-panel test-case-command-panel story-first-test-panel">
        <div className="story-command-header">
          <div>
            <h3>Generate Test Cases from User Stories</h3>
            <p>Select journey context, choose the exact user stories, then generate traceable test cases for those stories.</p>
          </div>
          <Badge tone={selectedStories.length ? 'success' : 'neutral'}>{selectedStories.length} stories selected</Badge>
        </div>

        <div className="journey-dropdown-layout">
          <label className="field journey-dropdown-field">
            <span>Add Journey Context</span>
            <select value={journeyPickerValue} onChange={addJourneyFromDropdown} disabled={!journeys.length || !availableJourneyCount}>
              <option value="">{journeys.length ? availableJourneyCount ? 'Choose journey maps to reveal user stories' : 'All journey maps selected' : 'No journey maps available'}</option>
              {journeys.map((journey) => (
                <option key={journey.journey_id} value={journey.journey_id} disabled={selectedJourneySet.has(journey.journey_id)}>
                  {getJourneyLabel(journey)}
                </option>
              ))}
            </select>
          </label>
          <div className="journey-dropdown-actions">
            <button className="secondary-button" onClick={selectAllJourneys} disabled={!journeys.length}>Select All Journeys</button>
            <button className="secondary-button" onClick={clearSelection} disabled={!selectedJourneys.length && !selectedStories.length}>Clear</button>
          </div>
        </div>

        <div className="selected-journey-summary compact-selection-summary">
          <div className="selected-journey-summary-head">
            <strong>Selected Journey Context</strong>
            <span>{selectedJourneys.length ? `${selectedJourneys.length} journey map${selectedJourneys.length > 1 ? 's' : ''}` : 'No journey maps selected'}</span>
          </div>
          {selectedJourneyItems.length ? (
            <div className="selected-journey-chips">
              {selectedJourneyItems.map((journey) => (
                <button key={journey.journey_id} type="button" className="selected-journey-chip" onClick={() => removeSelectedJourney(journey.journey_id)} title="Remove journey">
                  <span>{getJourneyLabel(journey)}</span>
                  <strong>Remove</strong>
                </button>
              ))}
            </div>
          ) : (
            <p className="selected-journey-empty">Choose journey maps to load their generated user stories.</p>
          )}
        </div>

        <div className="story-command-actions workflow-primary-actions">
          <button onClick={generate} disabled={generating || loading || !selectedStories.length}>{generating ? 'Generating Test Cases...' : 'Generate Test Cases'}</button>
          <button className="secondary-button" onClick={selectAllVisibleStories} disabled={!selectedJourneyStories.length}>Select All Stories</button>
          <button className="secondary-button" onClick={clearStorySelection} disabled={!selectedStories.length}>Clear Stories</button>
        </div>

        <div className="notification-row">
          {message && <Badge tone={message.includes('Generated') ? 'success' : 'warning'}>{message}</Badge>}
          <Badge tone="info">Synced: {generationMeta.jira_synced_count}</Badge>
          <Badge tone={generationMeta.jira_failed_count ? 'warning' : 'success'}>Local only: {generationMeta.jira_failed_count}</Badge>
        </div>
      </div>

      {selectedJourneys.length ? (
        <Card title="Select User Stories for Test Creation" subtitle="Only stories from selected journey maps are shown. Test cases will be generated only for checked stories.">
          <div className="story-group-stack test-case-mapping-stack">
            {selectedJourneyItems.map((journey) => {
              const journeyStories = storiesByJourney[journey.journey_id] ?? []
              return (
                <section key={journey.journey_id} className="story-group test-case-mapping-group">
                  <div className="story-group-head test-case-mapping-head">
                    <div>
                      <h3>{getJourneyLabel(journey)}</h3>
                      <p>{journey.journey_id}</p>
                    </div>
                    <Badge tone={journeyStories.length ? 'success' : 'neutral'}>{journeyStories.length} stories</Badge>
                  </div>
                  {journeyStories.length ? (
                    <div className="story-selection-list">
                      {journeyStories.map((story) => (
                        <label key={story.story_id} className={`story-selection-row ${selectedStorySet.has(story.story_id) ? 'story-selection-row-selected' : ''}`}>
                          <input type="checkbox" checked={selectedStorySet.has(story.story_id)} onChange={() => toggleStory(story.story_id)} />
                          <div>
                            <strong>{getStoryLabel(story)}</strong>
                            <span>{story.story_id}</span>
                          </div>
                          <Badge tone="neutral">{story.module || 'User Story'}</Badge>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <div className="story-empty-inline test-case-story-empty">
                      <strong>No user stories found for this journey.</strong>
                      <span>Go back to Step 2 and generate user stories before creating test cases.</span>
                    </div>
                  )}
                </section>
              )
            })}
          </div>
        </Card>
      ) : (
        <EmptyState title="Select journey context" description="Choose one or more journey maps above to reveal the user stories available for test-case generation." />
      )}

      {selectedStories.length ? (
        visibleTestCases.length ? (
          <div className="test-case-results-panel">
            <Card title="Generated Test Cases by User Story" subtitle="Only test cases linked to selected user stories are shown.">
              <div className="story-group-stack generated-case-story-stack">
                {selectedStoryItems.map((story) => {
                  const storyCases = testCasesByStory[story.story_id] ?? []
                  return (
                    <section key={story.story_id} className="story-group test-case-mapping-group">
                      <div className="story-group-head test-case-mapping-head">
                        <div>
                          <h3>{getStoryLabel(story)}</h3>
                          <p>{story.story_id}</p>
                        </div>
                        <Badge tone={storyCases.length ? 'success' : 'neutral'}>{storyCases.length} test cases</Badge>
                      </div>
                      {storyCases.length ? (
                        <Table
                          columns={['Case ID', 'Title', 'Jira', 'Type']}
                          rows={storyCases.map((item) => (
                            <tr key={item.test_case_id}>
                              <td>{item.test_case_id}</td>
                              <td>{item.title}</td>
                              <td>
                                {item.jira_url ? (
                                  <a href={item.jira_url} target="_blank" rel="noreferrer">{item.jira_key || 'Open Jira'}</a>
                                ) : (
                                  <Badge tone={item.sync_status === 'local' ? 'warning' : 'neutral'}>{item.sync_status || 'local'}</Badge>
                                )}
                              </td>
                              <td>{item.jira_issue_type ? <Badge tone="info">{item.jira_issue_type}</Badge> : <Badge tone="neutral">local</Badge>}</td>
                            </tr>
                          ))}
                        />
                      ) : (
                        <div className="story-empty-inline test-case-story-empty">
                          <strong>No generated test cases yet.</strong>
                          <span>Click Generate Test Cases to create tests for this story.</span>
                        </div>
                      )}
                    </section>
                  )
                })}
              </div>
            </Card>
          </div>
        ) : (
          <div className="test-case-results-empty"><EmptyState title="No test cases for selected stories" description="Generate test cases after choosing the user stories above." /></div>
        )
      ) : null}
    </Card>
  )
}
