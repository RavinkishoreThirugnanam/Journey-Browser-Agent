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

export function TestScriptsPage() {
  const { data, loading, refetch } = useFetch(api.getTestScripts, [])
  const scripts = data?.items ?? []
  const [journeys, setJourneys] = useState([])
  const [stories, setStories] = useState([])
  const [testCases, setTestCases] = useState([])
  const [selectedJourneys, setSelectedJourneys] = useState([])
  const [selectedStories, setSelectedStories] = useState([])
  const [selectedTestCases, setSelectedTestCases] = useState([])
  const [journeyPickerValue, setJourneyPickerValue] = useState('')
  const [storyPickerValue, setStoryPickerValue] = useState('')
  const [testCasePickerValue, setTestCasePickerValue] = useState('')
  const [message, setMessage] = useState('')
  const [generating, setGenerating] = useState(false)

  const loadSources = async () => {
    const [journeyResult, storyResult, testCaseResult] = await Promise.allSettled([
      api.getJourneys(),
      api.getUserStories(),
      api.getTestCases(),
    ])
    setJourneys(journeyResult.status === 'fulfilled' ? journeyResult.value?.items ?? journeyResult.value ?? [] : [])
    setStories(storyResult.status === 'fulfilled' ? storyResult.value?.items ?? storyResult.value ?? [] : [])
    setTestCases(testCaseResult.status === 'fulfilled' ? testCaseResult.value?.items ?? testCaseResult.value ?? [] : [])
  }

  useEffect(() => {
    loadSources().catch(() => {})
  }, [])

  const selectedJourneySet = useMemo(() => new Set(selectedJourneys), [selectedJourneys])
  const selectedStorySet = useMemo(() => new Set(selectedStories), [selectedStories])
  const selectedTestCaseSet = useMemo(() => new Set(selectedTestCases), [selectedTestCases])

  const selectedJourneyItems = useMemo(() => journeys.filter((journey) => selectedJourneySet.has(journey.journey_id)), [journeys, selectedJourneySet])
  const selectedStoryItems = useMemo(() => stories.filter((story) => selectedStorySet.has(story.story_id)), [stories, selectedStorySet])
  const selectedTestCaseItems = useMemo(() => testCases.filter((testCase) => selectedTestCaseSet.has(testCase.test_case_id)), [testCases, selectedTestCaseSet])

  const availableJourneyCount = journeys.filter((journey) => !selectedJourneySet.has(journey.journey_id)).length
  const availableStoryItems = useMemo(() => {
    if (!selectedJourneys.length) return []
    return stories.filter((story) => selectedJourneySet.has(story.journey_id))
  }, [stories, selectedJourneys, selectedJourneySet])
  const availableStoryCount = availableStoryItems.filter((story) => !selectedStorySet.has(story.story_id)).length
  const availableTestCaseItems = useMemo(() => {
    if (!selectedStories.length) return []
    return testCases.filter((testCase) => selectedStorySet.has(testCase.user_story_id))
  }, [testCases, selectedStories, selectedStorySet])
  const availableTestCaseCount = availableTestCaseItems.filter((testCase) => !selectedTestCaseSet.has(testCase.test_case_id)).length

  const scriptsForSelection = useMemo(() => {
    if (!selectedTestCases.length) return []
    return scripts.filter((script) => selectedTestCaseSet.has(script.test_case_id))
  }, [scripts, selectedTestCases, selectedTestCaseSet])

  const scriptsByTestCase = useMemo(() => {
    return scriptsForSelection.reduce((acc, script) => {
      const testCaseId = script.test_case_id || 'unknown'
      if (!acc[testCaseId]) acc[testCaseId] = []
      acc[testCaseId].push(script)
      return acc
    }, {})
  }, [scriptsForSelection])

  const getJourneyLabel = (journey) => journey?.journey_title || journey?.source_url || journey?.application_url || 'Journey map'
  const getStoryLabel = (story) => story?.summary || story?.title || 'User story'
  const getTestCaseLabel = (testCase) => testCase?.title || testCase?.test_case_title || 'Test case'

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

  const addStoryFromDropdown = (event) => {
    const storyId = event.target.value
    if (!storyId) return
    if (storyId === '__all__') {
      selectAllStories()
      return
    }
    setSelectedStories((current) => (current.includes(storyId) ? current : [...current, storyId]))
    setStoryPickerValue('')
  }

  const addTestCaseFromDropdown = (event) => {
    const testCaseId = event.target.value
    if (!testCaseId) return
    if (testCaseId === '__all__') {
      selectAllTestCases()
      return
    }
    setSelectedTestCases((current) => (current.includes(testCaseId) ? current : [...current, testCaseId]))
    setTestCasePickerValue('')
  }

  const selectAllJourneys = () => {
    setSelectedJourneys(journeys.map((journey) => journey.journey_id))
    setSelectedStories([])
    setSelectedTestCases([])
    setJourneyPickerValue('')
    setStoryPickerValue('')
    setTestCasePickerValue('')
  }

  const selectAllStories = () => {
    setSelectedStories(availableStoryItems.map((story) => story.story_id))
    setSelectedTestCases([])
    setStoryPickerValue('')
    setTestCasePickerValue('')
  }

  const selectAllTestCases = () => {
    setSelectedTestCases(availableTestCaseItems.map((testCase) => testCase.test_case_id))
    setTestCasePickerValue('')
  }

  const clearAll = () => {
    setSelectedJourneys([])
    setSelectedStories([])
    setSelectedTestCases([])
    setJourneyPickerValue('')
    setStoryPickerValue('')
    setTestCasePickerValue('')
  }

  const removeJourney = (journeyId) => {
    const removedStoryIds = stories.filter((story) => story.journey_id === journeyId).map((story) => story.story_id)
    const removedStorySet = new Set(removedStoryIds)
    const removedTestCaseIds = testCases.filter((testCase) => removedStorySet.has(testCase.user_story_id)).map((testCase) => testCase.test_case_id)
    const removedTestCaseSet = new Set(removedTestCaseIds)
    setSelectedJourneys((current) => current.filter((id) => id !== journeyId))
    setSelectedStories((current) => current.filter((id) => !removedStorySet.has(id)))
    setSelectedTestCases((current) => current.filter((id) => !removedTestCaseSet.has(id)))
  }

  const removeStory = (storyId) => {
    const removedTestCaseSet = new Set(testCases.filter((testCase) => testCase.user_story_id === storyId).map((testCase) => testCase.test_case_id))
    setSelectedStories((current) => current.filter((id) => id !== storyId))
    setSelectedTestCases((current) => current.filter((id) => !removedTestCaseSet.has(id)))
  }

  const removeTestCase = (testCaseId) => {
    setSelectedTestCases((current) => current.filter((id) => id !== testCaseId))
  }

  const generate = async () => {
    setMessage('')
    if (!selectedTestCases.length) {
      setMessage('Select the test cases you want to convert into Gherkin and JavaScript scripts.')
      return
    }
    setGenerating(true)
    try {
      const result = await api.generateTestScripts({ test_case_ids: selectedTestCases })
      setMessage(`Generated ${result?.count ?? 0} traceable scripts for ${selectedTestCases.length} selected test cases.`)
      await refetch()
      await loadSources()
    } catch (error) {
      setMessage(error?.message || 'Unable to generate test scripts.')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Card
      title="Test Scripts"
      subtitle="Choose test sources, generate scripts, and download artifacts from one focused workspace."
      actions={<button onClick={refetch} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>}
    >
      <div className="workflow-minimal-shell script-minimal-shell">
        <div className="workflow-minimal-toolbar">
          <div className="workflow-minimal-intro">
            <div>
              <span className="eyebrow">Script generation</span>
              <h3>Build scripts from traceable test cases</h3>
              <p>Choose journey, story, and test-case context in order. The available cases and generated artifacts stay visible below.</p>
            </div>
            <div className="workflow-minimal-counts" aria-label="Current script source selection">
              <span><strong>{selectedJourneys.length}</strong> journeys</span>
              <span><strong>{selectedStories.length}</strong> stories</span>
              <span><strong>{selectedTestCases.length}</strong> test cases</span>
              <span><strong>{scriptsForSelection.length}</strong> scripts</span>
            </div>
          </div>

          <div className="script-minimal-source-grid">
            <label className="field workflow-minimal-picker">
              <span>1. Journey context</span>
              <select value={journeyPickerValue} onChange={addJourneyFromDropdown} disabled={!journeys.length || !availableJourneyCount}>
                <option value="">{journeys.length ? availableJourneyCount ? 'Choose a journey map' : 'All journey maps selected' : 'No journey maps available'}</option>
                <option value="__all__" disabled={!availableJourneyCount}>Select all journey maps</option>
                {journeys.map((journey) => (
                  <option key={journey.journey_id} value={journey.journey_id} disabled={selectedJourneySet.has(journey.journey_id)}>{getJourneyLabel(journey)}</option>
                ))}
              </select>
            </label>

            <label className="field workflow-minimal-picker">
              <span>2. User stories</span>
              <select value={storyPickerValue} onChange={addStoryFromDropdown} disabled={!availableStoryItems.length || !availableStoryCount}>
                <option value="">{selectedJourneys.length ? availableStoryCount ? 'Choose a user story' : 'All available stories selected' : 'Select journey context first'}</option>
                <option value="__all__" disabled={!availableStoryCount}>Select all available stories</option>
                {availableStoryItems.map((story) => (
                  <option key={story.story_id} value={story.story_id} disabled={selectedStorySet.has(story.story_id)}>{getStoryLabel(story)}</option>
                ))}
              </select>
            </label>

            <label className="field workflow-minimal-picker">
              <span>3. Test cases</span>
              <select value={testCasePickerValue} onChange={addTestCaseFromDropdown} disabled={!availableTestCaseItems.length || !availableTestCaseCount}>
                <option value="">{selectedStories.length ? availableTestCaseCount ? 'Choose a test case' : 'All available cases selected' : 'Select user stories first'}</option>
                <option value="__all__" disabled={!availableTestCaseCount}>Select all available test cases</option>
                {availableTestCaseItems.map((testCase) => (
                  <option key={testCase.test_case_id} value={testCase.test_case_id} disabled={selectedTestCaseSet.has(testCase.test_case_id)}>{getTestCaseLabel(testCase)}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="workflow-minimal-actions script-minimal-quick-actions">
            <button type="button" className="secondary-button" onClick={clearAll} disabled={!selectedJourneys.length && !selectedStories.length && !selectedTestCases.length}>Clear</button>
          </div>

          {(selectedJourneyItems.length || selectedStoryItems.length || selectedTestCaseItems.length) ? (
            <div className="workflow-minimal-selection">
              <strong>Current selection</strong>
              <div className="workflow-minimal-chips workflow-minimal-context-chips">
                {selectedJourneyItems.map((journey) => (
                  <button key={`journey-${journey.journey_id}`} type="button" onClick={() => removeJourney(journey.journey_id)} title="Remove journey">
                    <small>Journey</small><span>{getJourneyLabel(journey)}</span><strong aria-hidden="true">×</strong>
                  </button>
                ))}
                {selectedStoryItems.map((story) => (
                  <button key={`story-${story.story_id}`} type="button" onClick={() => removeStory(story.story_id)} title="Remove story">
                    <small>Story</small><span>{getStoryLabel(story)}</span><strong aria-hidden="true">×</strong>
                  </button>
                ))}
                {selectedTestCaseItems.map((testCase) => (
                  <button key={`case-${testCase.test_case_id}`} type="button" onClick={() => removeTestCase(testCase.test_case_id)} title="Remove test case">
                    <small>Case</small><span>{getTestCaseLabel(testCase)}</span><strong aria-hidden="true">×</strong>
                  </button>
                ))}
              </div>
            </div>
          ) : <p className="workflow-minimal-hint">Start by selecting journey context. Stories and test cases will become available automatically.</p>}

          {message ? <div className="workflow-minimal-message"><Badge tone={message.includes('Generated') ? 'success' : 'warning'}>{message}</Badge></div> : null}
        </div>

        <div className="workflow-minimal-workspace">
          <div className="workflow-minimal-heading">
            <div>
              <h3>Available test cases</h3>
              <p>Select the exact cases that should become Gherkin and JavaScript artifacts.</p>
            </div>
            <div className="workflow-minimal-actions">
              <Badge tone={selectedTestCases.length ? 'success' : 'neutral'}>{selectedTestCases.length} selected</Badge>
            </div>
          </div>

          {selectedStories.length && availableTestCaseItems.length ? (
            <div className="script-minimal-case-list">
              {availableTestCaseItems.map((testCase) => {
                const story = stories.find((candidate) => candidate.story_id === testCase.user_story_id)
                return (
                  <label key={testCase.test_case_id} className={`script-minimal-case-row ${selectedTestCaseSet.has(testCase.test_case_id) ? 'selected' : ''}`}>
                    <input type="checkbox" checked={selectedTestCaseSet.has(testCase.test_case_id)} onChange={() => selectedTestCaseSet.has(testCase.test_case_id) ? removeTestCase(testCase.test_case_id) : setSelectedTestCases((current) => [...current, testCase.test_case_id])} />
                    <div>
                      <strong>{getTestCaseLabel(testCase)}</strong>
                    </div>
                    <span>{getStoryLabel(story)}</span>
                    <Badge tone="neutral">{testCase.test_case_type || 'Functional'}</Badge>
                  </label>
                )
              })}
            </div>
          ) : (
            <div className="workflow-minimal-empty compact">
              <strong>{selectedStories.length ? 'No test cases exist for the selected stories.' : 'Select user stories to reveal test cases.'}</strong>
              <span>{selectedStories.length ? 'Generate test cases in Step 3, then return here.' : 'Use the ordered selectors above to narrow the available sources.'}</span>
            </div>
          )}
          <div className="script-minimal-bottom-actions">
            <button type="button" onClick={generate} disabled={generating || loading || !selectedTestCases.length}>{generating ? 'Generating...' : 'Generate Test Scripts'}</button>
          </div>
        </div>

        <div className="workflow-minimal-workspace">
          <div className="workflow-minimal-heading">
            <div>
              <h3>Generated scripts</h3>
              <p>Download both artifacts directly from the matching test-case row.</p>
            </div>
            <Badge tone={scriptsForSelection.length ? 'success' : 'neutral'}>{scriptsForSelection.length} scripts</Badge>
          </div>

          {scriptsForSelection.length ? (
            <Table
              columns={['Script', 'Test Case', 'Source Evidence', 'Artifacts']}
              rows={scriptsForSelection.map((item) => {
                const testCase = testCases.find((candidate) => candidate.test_case_id === item.test_case_id)
                const evidenceCount = Number(item.source_evidence_count || 0)
                return (
                  <tr key={item.script_id}>
                    <td><strong>Generated script</strong></td>
                    <td><strong>{getTestCaseLabel(testCase)}</strong></td>
                    <td><Badge tone={evidenceCount ? "success" : "warning"}>{evidenceCount ? `${evidenceCount} linked observations` : "Evidence unavailable"}</Badge></td>
                    <td>
                      <div className="table-actions script-artifact-actions">
                        <button className="button-secondary" onClick={() => api.downloadTestScriptArtifact(item.script_id, 'feature', item.feature_filename || `${item.script_id}.feature`)}>Gherkin</button>
                        <button className="button-secondary" onClick={() => api.downloadTestScriptArtifact(item.script_id, 'javascript', item.javascript_filename || `${item.script_id}.js`)}>JavaScript</button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            />
          ) : (
            <div className="workflow-minimal-empty compact">
              <strong>No scripts for the current selection.</strong>
              <span>Select test cases above and generate scripts to see downloadable artifacts here.</span>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
