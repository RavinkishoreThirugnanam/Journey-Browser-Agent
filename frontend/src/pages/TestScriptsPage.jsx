import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Badge, Card, Table } from '../components/Ui'
import { useFetch } from '../hooks/useFetch'

export function TestScriptsPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const requestedJourneyId = searchParams.get('journey') || ''
  const requestedJourneyIds = (searchParams.get('journeys') || '').split(',').filter(Boolean)
  const { data, loading, refetch } = useFetch(api.getTestScripts, [])
  const scripts = data?.items ?? []
  const [journeys, setJourneys] = useState([])
  const [stories, setStories] = useState([])
  const [testCases, setTestCases] = useState([])
  const [selectedJourneys, setSelectedJourneys] = useState([])
  const [selectedStories, setSelectedStories] = useState([])
  const [selectedTestCases, setSelectedTestCases] = useState([])
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

  useEffect(() => {
    if (!journeys.length) return
    const availableIds = new Set(journeys.map((journey) => journey.journey_id))
    const requestedIds = requestedJourneyIds.length ? requestedJourneyIds : (requestedJourneyId ? [requestedJourneyId] : [])
    const validIds = requestedIds.filter((journeyId) => availableIds.has(journeyId))
    if (!validIds.length) return
    setSelectedJourneys(validIds)
    setSelectedStories([])
    setSelectedTestCases([])
  }, [journeys, requestedJourneyId, searchParams.get('journeys')])

  const selectedJourneySet = useMemo(() => new Set(selectedJourneys), [selectedJourneys])
  const selectedStorySet = useMemo(() => new Set(selectedStories), [selectedStories])
  const selectedTestCaseSet = useMemo(() => new Set(selectedTestCases), [selectedTestCases])
  const selectedJourneyItems = useMemo(() => journeys.filter((journey) => selectedJourneySet.has(journey.journey_id)), [journeys, selectedJourneySet])

  const availableStoryItems = useMemo(() => {
    if (!selectedJourneys.length) return []
    return stories.filter((story) => selectedJourneySet.has(story.journey_id))
  }, [stories, selectedJourneys, selectedJourneySet])

  const availableTestCaseItems = useMemo(() => {
    if (!selectedJourneys.length) return []
    const journeyStoryIds = new Set(availableStoryItems.map((story) => story.story_id))
    return testCases.filter((testCase) => (
      selectedJourneySet.has(testCase.journey_id) || journeyStoryIds.has(testCase.user_story_id)
    ))
  }, [testCases, selectedJourneys, selectedJourneySet, availableStoryItems])

  useEffect(() => {
    setSelectedStories(availableStoryItems.map((story) => story.story_id))
    setSelectedTestCases(availableTestCaseItems.map((testCase) => testCase.test_case_id))
  }, [availableStoryItems, availableTestCaseItems])

  const scriptsForSelection = useMemo(() => {
    if (!selectedTestCases.length) return []
    return scripts.filter((script) => selectedTestCaseSet.has(script.test_case_id))
  }, [scripts, selectedTestCases, selectedTestCaseSet])

  const getJourneyLabel = (journey) => journey?.journey_title || journey?.source_url || journey?.application_url || 'Journey map'
  const getStoryLabel = (story) => story?.summary || story?.title || 'User story'
  const getTestCaseLabel = (testCase) => testCase?.title || testCase?.test_case_title || 'Test case'

  const selectAllTestCases = () => {
    setSelectedTestCases(availableTestCaseItems.map((testCase) => testCase.test_case_id))
  }

  const clearAll = () => {
    setSelectedJourneys([])
    setSelectedStories([])
    setSelectedTestCases([])
  }

  const toggleTestCase = (testCaseId) => {
    setSelectedTestCases((current) => (
      current.includes(testCaseId)
        ? current.filter((id) => id !== testCaseId)
        : [...current, testCaseId]
    ))
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

  const allAvailableCasesSelected = availableTestCaseItems.length > 0 && availableTestCaseItems.every((testCase) => selectedTestCaseSet.has(testCase.test_case_id))
  const allJourneysSelected = selectedJourneys.length === journeys.length && journeys.length > 1
  const journeySelectionValue = allJourneysSelected ? '__all__' : (selectedJourneys.length === 1 ? selectedJourneys[0] : '')
  const selectedJourneyLabel = allJourneysSelected
    ? 'All Journey Maps'
    : (selectedJourneyItems[0] ? getJourneyLabel(selectedJourneyItems[0]) : 'Test Scripts')

  return (
    <Card
      className="test-script-page-flat"
      title="Test Scripts"
      subtitle="Select a journey map to review its scripts or generate updated Gherkin and JavaScript files."
    >
      <div className="test-script-simple">
        <div className="test-script-source-row">
          <div className="test-script-source-grid single">
            <label className="field workflow-minimal-picker">
              <span>Journey map</span>
              <select value={journeySelectionValue} onChange={(event) => {
                const journeyId = event.target.value
                setSelectedJourneys(journeyId === '__all__' ? journeys.map((journey) => journey.journey_id) : (journeyId ? [journeyId] : []))
                setSelectedStories([])
                setSelectedTestCases([])
              }} disabled={!journeys.length}>
                <option value="">{journeys.length ? 'Choose a journey map' : 'No journey maps available'}</option>
                {journeys.length > 1 ? <option value="__all__">Select All Journey Maps</option> : null}
                {journeys.map((journey) => (
                  <option key={journey.journey_id} value={journey.journey_id}>{getJourneyLabel(journey)}</option>
                ))}
              </select>
            </label>

          </div>
          <button type="button" className="secondary-button" onClick={clearAll} disabled={!selectedJourneys.length && !selectedStories.length && !selectedTestCases.length}>Clear</button>
        </div>

        {message ? <div className="test-script-message"><Badge tone={message.includes('Generated') ? 'success' : 'warning'}>{message}</Badge></div> : null}

        <section className="test-script-section">
          <div className="test-script-section-heading">
            <div>
              <h3>Available test cases</h3>
              <p>The selected journey&apos;s test cases are used to create Gherkin and JavaScript artifacts.</p>
            </div>
            {!scriptsForSelection.length ? (
              <button type="button" onClick={generate} disabled={generating || loading || !selectedTestCases.length}>
                {generating ? 'Generating...' : 'Generate Test Scripts'}
              </button>
            ) : null}
          </div>

          {selectedJourneys.length && availableTestCaseItems.length ? (
            <div className="test-script-table-wrap">
              <table className="test-script-table">
                <thead><tr>
                  <th><input type="checkbox" aria-label="Select all available test cases" checked={allAvailableCasesSelected} onChange={() => allAvailableCasesSelected ? setSelectedTestCases([]) : selectAllTestCases()} /></th>
                  <th>Test Case</th><th>User Story</th><th>Type</th>
                </tr></thead>
                <tbody>{availableTestCaseItems.map((testCase) => {
                  const story = stories.find((candidate) => candidate.story_id === testCase.user_story_id)
                  const selected = selectedTestCaseSet.has(testCase.test_case_id)
                  return (
                    <tr key={testCase.test_case_id} className={selected ? 'selected' : ''} onClick={() => toggleTestCase(testCase.test_case_id)}>
                      <td><input type="checkbox" checked={selected} onClick={(event) => event.stopPropagation()} onChange={() => toggleTestCase(testCase.test_case_id)} /></td>
                      <td><strong>{getTestCaseLabel(testCase)}</strong></td>
                      <td>{getStoryLabel(story)}</td>
                      <td><span className="user-story-category">{testCase.test_case_type || 'Functional'}</span></td>
                    </tr>
                  )
                })}</tbody>
              </table>
            </div>
          ) : (
            <div className="test-script-empty">
              <strong>{selectedJourneys.length ? 'No test cases exist for the selected journey.' : 'Select a journey map to reveal test cases.'}</strong>
              <span>{selectedJourneys.length ? 'Generate test cases in Stage 3, then return here.' : 'Choose a journey map above.'}</span>
            </div>
          )}
        </section>

        <section className="test-script-section">
          <div className="test-script-section-heading">
            <div>
              <h3>Generated scripts</h3>
              <p>Download the Gherkin feature and JavaScript automation files from each test-case row.</p>
            </div>
            <Badge tone={scriptsForSelection.length ? 'success' : 'neutral'}>{scriptsForSelection.length} scripts</Badge>
          </div>

          {scriptsForSelection.length ? (
            <Table
              columns={['Test Case', 'Source Evidence', 'Gherkin File', 'JavaScript File']}
              rows={scriptsForSelection.map((item) => {
                const testCase = testCases.find((candidate) => candidate.test_case_id === item.test_case_id)
                const evidenceCount = Number(item.source_evidence_count || 0)
                return (
                  <tr key={item.script_id}>
                    <td><strong>{getTestCaseLabel(testCase)}</strong></td>
                    <td><Badge tone={evidenceCount ? 'success' : 'warning'}>{evidenceCount ? `${evidenceCount} linked observations` : 'Evidence unavailable'}</Badge></td>
                    <td><button className="secondary-button test-script-download" onClick={() => api.downloadTestScriptArtifact(item.script_id, 'feature', item.feature_filename || `${item.script_id}.feature`)}>Download .feature</button></td>
                    <td><button className="secondary-button test-script-download" onClick={() => api.downloadTestScriptArtifact(item.script_id, 'javascript', item.javascript_filename || `${item.script_id}.js`)}>Download .js</button></td>
                  </tr>
                )
              })}
            />
          ) : (
            <div className="test-script-empty">
              <strong>No scripts for the current selection.</strong>
              <span>Select test cases above and generate scripts to see downloadable artifacts here.</span>
            </div>
          )}
        </section>
      </div>

      <footer className="workflow-fixed-footer test-scripts-fixed-footer">
        <div className="workflow-fixed-stage"><strong>Stage 4 of 5</strong><span>&bull;</span><span>{selectedJourneyLabel}</span></div>
        <div className="workflow-fixed-actions">
          <button type="button" className="secondary-button" onClick={() => navigate(selectedJourneys.length === 1 ? `/tests?journey=${encodeURIComponent(selectedJourneys[0])}` : '/tests')}>Back to Test Cases</button>
          <button type="button" onClick={() => navigate(selectedJourneys.length === 1 ? `/export?journey=${encodeURIComponent(selectedJourneys[0])}` : `/export?journeys=${encodeURIComponent(selectedJourneys.join(','))}`)} disabled={!scriptsForSelection.length}>Continue to Review <span aria-hidden="true">&rarr;</span></button>
        </div>
      </footer>
    </Card>
  )
}
