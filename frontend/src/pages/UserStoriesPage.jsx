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

function jiraRefreshLabel(story) {
  const status = String(story?.jira_sync_status || '').toLowerCase()
  if (status === 'updated_from_jira') return 'Updated from Jira'
  if (status === 'up_to_date') return 'Up to date'
  if (status === 'refresh_failed') return 'Refresh failed'
  if (status === 'synced') return 'Created in Jira'
  return 'Local'
}

function jiraRefreshTime(story) {
  if (!story?.jira_last_refreshed_at) return ''
  const value = new Date(story.jira_last_refreshed_at)
  return Number.isNaN(value.getTime()) ? '' : 'Refreshed ' + value.toLocaleString()
}
export function UserStoriesPage() {
  const { data, loading, refetch } = useFetch(api.getUserStories, [])
  const items = data?.items ?? []
  const [journeys, setJourneys] = useState([])
  const [selectedJourneys, setSelectedJourneys] = useState([])
  const [generating, setGenerating] = useState(false)
  const [refreshingJira, setRefreshingJira] = useState(false)
  const [deletingStoryId, setDeletingStoryId] = useState('')
  const [message, setMessage] = useState('')
  const [journeyPickerValue, setJourneyPickerValue] = useState('')

  useEffect(() => {
    api.getJourneys().then((d) => setJourneys(d.items ?? d ?? [])).catch(() => setJourneys([]))
  }, [])

  const storiesByJourney = useMemo(() => {
    return items.reduce((acc, story) => {
      const journeyId = story.journey_id || 'unknown'
      if (!acc[journeyId]) acc[journeyId] = []
      acc[journeyId].push(story)
      return acc
    }, {})
  }, [items])

  const nestedJourneys = useMemo(() => {
    return journeys.map((journey) => ({
      ...journey,
      uiPages: journey?.page_url_ui_element_section?.ui_elements_data ?? [],
    }))
  }, [journeys])

  const selectedJourneySet = new Set(selectedJourneys)
  const selectedJourneyItems = useMemo(() => journeys.filter((journey) => selectedJourneySet.has(journey.journey_id)), [journeys, selectedJourneys])
  const selectedStories = useMemo(() => items.filter((story) => selectedJourneySet.has(story.journey_id)), [items, selectedJourneys])
  const jiraLinkedSelectedStories = useMemo(() => selectedStories.filter((story) => story.jira_key), [selectedStories])
  const selectedStoriesByJourney = useMemo(() => {
    return selectedJourneyItems.reduce((acc, journey) => {
      acc[journey.journey_id] = storiesByJourney[journey.journey_id] ?? []
      return acc
    }, {})
  }, [selectedJourneyItems, storiesByJourney])
  const availableJourneyCount = journeys.filter((journey) => !selectedJourneySet.has(journey.journey_id)).length

  const selectAllJourneys = () => {
    setSelectedJourneys(journeys.map((journey) => journey.journey_id))
    setJourneyPickerValue('')
  }
  const clearSelection = () => {
    setSelectedJourneys([])
    setJourneyPickerValue('')
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
    if (journeyPickerValue === journeyId) setJourneyPickerValue('')
  }

  const getJourneyLabel = (journey) => journey?.journey_title || journey?.source_url || journey?.application_url || 'Journey map'
  const generationSourceLabel = (story) => {
    const source = String(story?.generation_source || '').toLowerCase()
    if (source === 'openai') return story?.generation_model ? 'OpenAI - ' + story.generation_model : 'OpenAI'
    if (source === 'fallback') return 'Local fallback'
    return 'Legacy'
  }
  const generationSourceTone = (story) => {
    const source = String(story?.generation_source || '').toLowerCase()
    if (source === 'openai') return 'success'
    if (source === 'fallback') return 'warning'
    return 'neutral'
  }

  const refreshStoriesFromJira = async () => {
    const storyIds = jiraLinkedSelectedStories.map((story) => story.story_id).filter(Boolean)
    if (!storyIds.length) {
      setMessage('No Jira-linked stories are available in the selected journeys.')
      return
    }
    setRefreshingJira(true)
    setMessage('')
    try {
      const result = await api.refreshUserStoriesFromJira({ story_ids: storyIds })
      await refetch()
      if (result?.failed) {
        setMessage('Updated ' + (result.updated ?? 0) + ' stories from Jira, but ' + result.failed + ' refreshes failed.')
      } else {
        setMessage('Jira refresh completed: ' + (result?.updated ?? 0) + ' updated and ' + (result?.unchanged ?? 0) + ' already current.')
      }
    } catch (error) {
      setMessage(error?.message || 'Unable to refresh user stories from Jira.')
    } finally {
      setRefreshingJira(false)
    }
  }
  const deleteStory = async (storyId) => {
    if (!storyId) return
    setMessage('')
    setDeletingStoryId(storyId)
    try {
      const result = await api.deleteUserStory(storyId)
      await refetch()
      setMessage('Deleted user story locally' + (result.test_cases_deleted ? ', ' + result.test_cases_deleted + ' related test case(s)' : '') + (result.test_scripts_deleted ? ', and ' + result.test_scripts_deleted + ' related script(s)' : '') + '.')
    } catch (error) {
      setMessage(error?.message || 'Unable to delete user story locally.')
    } finally {
      setDeletingStoryId('')
    }
  }

  const generateStories = async () => {
    setMessage('')
    if (!selectedJourneys.length) {
      setMessage('Select at least one journey map to generate user stories.')
      return
    }
    setGenerating(true)
    try {
      const result = await api.generateUserStories({ journey_ids: selectedJourneys })
      const generatedStories = result?.stories ?? []
      const generatedStoryIds = generatedStories.map((story) => story.story_id).filter(Boolean)
      let jiraSyncCount = 0
      let jiraSyncWarning = ''
      if (generatedStoryIds.length) {
        try {
          const syncResult = await api.syncUserStoriesToJira({ story_ids: generatedStoryIds })
          jiraSyncCount = syncResult?.items?.length ?? 0
        } catch (error) {
          jiraSyncWarning = error?.message || 'Jira sync failed; stories were saved locally.'
        }
      }
      const bundleSource = String(result?.generation_source || '').toLowerCase()
      const bundleModel = result?.generation_model || ''
      const warning = result?.generation_warning || ''
      const sourceSummary = bundleSource === 'openai'
        ? `OpenAI${bundleModel ? ` - ${bundleModel}` : ''}`
        : Array.from(new Set(generatedStories.map(generationSourceLabel))).join(', ') || 'Unknown source'

      if (warning) {
        setMessage(`Generated ${generatedStories.length} user stories using ${sourceSummary}. LLM fallback reason: ${warning}`)
      } else if (jiraSyncWarning) {
        setMessage('Generated ' + generatedStories.length + ' user stories using ' + sourceSummary + '. Saved locally, but Jira sync failed: ' + jiraSyncWarning)
      } else {
        setMessage('Generated ' + generatedStories.length + ' user stories using ' + sourceSummary + '; ' + jiraSyncCount + ' created in Jira and saved locally.')
      }

      await refetch()
    } catch (error) {
      setMessage(error?.message || 'Unable to generate user stories.')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Card
      title="User Stories"
      subtitle="Select journey context, generate stories, and review every result in one readable workspace."
      actions={<button onClick={refetch} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>}
    >
      <div className="workflow-minimal-shell">
        <div className="workflow-minimal-toolbar">
          <div className="workflow-minimal-intro">
            <div>
              <span className="eyebrow">Story creation</span>
              <h3>Generate stories from journey maps</h3>
              <p>Add the journeys you want to cover. Existing and newly generated stories appear together below.</p>
            </div>
            <div className="workflow-minimal-counts" aria-label="Current user story selection">
              <span><strong>{selectedJourneys.length}</strong> journeys</span>
              <span><strong>{selectedStories.length}</strong> stories</span>
            </div>
          </div>

          <div className="workflow-minimal-controls">
            <label className="field workflow-minimal-picker">
              <span>Add journey context</span>
              <select value={journeyPickerValue} onChange={addJourneyFromDropdown} disabled={!journeys.length || !availableJourneyCount}>
                <option value="">{journeys.length ? availableJourneyCount ? 'Choose a journey map' : 'All journey maps selected' : 'No journey maps available'}</option>
                <option value="__all__" disabled={!availableJourneyCount}>Select all journey maps</option>
                {nestedJourneys.map((journey) => (
                  <option key={journey.journey_id} value={journey.journey_id} disabled={selectedJourneySet.has(journey.journey_id)}>
                    {getJourneyLabel(journey)}
                  </option>
                ))}
              </select>
            </label>
            <div className="workflow-minimal-actions">
              <button type="button" className="secondary-button" onClick={clearSelection} disabled={!selectedJourneys.length}>Clear</button>
              <button type="button" onClick={generateStories} disabled={generating || loading || !selectedJourneys.length}>
                {generating ? 'Generating...' : 'Generate User Stories'}
              </button>
            </div>
          </div>

          {selectedJourneyItems.length ? (
            <div className="workflow-minimal-chips" aria-label="Selected journeys">
              {selectedJourneyItems.map((journey) => (
                <button key={journey.journey_id} type="button" onClick={() => removeSelectedJourney(journey.journey_id)} title="Remove journey">
                  <span>{getJourneyLabel(journey)}</span><strong aria-hidden="true">×</strong>
                </button>
              ))}
            </div>
          ) : <p className="workflow-minimal-hint">Select a journey map to view or generate its user stories.</p>}

          {message ? <div className="workflow-minimal-message"><Badge tone={message.toLowerCase().includes('unable') || message.toLowerCase().includes('failed') ? 'danger' : 'success'}>{message}</Badge></div> : null}
        </div>

        {selectedJourneys.length ? (
          <div className="workflow-minimal-workspace">
            <div className="workflow-minimal-heading">
              <div>
                <h3>Generated user stories</h3>
                <p>All stories from the selected journeys are shown together. Journey and generation context remain visible on every row.</p>
              </div>
              <div className="workflow-minimal-heading-actions">
                <Badge tone={selectedStories.length ? 'success' : 'neutral'}>{selectedStories.length} stories</Badge>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={refreshStoriesFromJira}
                  disabled={refreshingJira || !jiraLinkedSelectedStories.length}
                >
                  {refreshingJira ? 'Refreshing Jira...' : 'Refresh from Jira'}
                </button>
              </div>
            </div>

            {selectedStories.length ? (
              <Table
                columns={['Story', 'Journey', 'Source', 'Epic', 'Module / Component', 'Jira', 'Action']}
                rows={selectedStories.map((item) => {
                  const journey = journeys.find((candidate) => candidate.journey_id === item.journey_id)
                  return (
                    <tr key={item.story_id}>
                      <td><strong>{item.summary}</strong></td>
                      <td><strong>{getJourneyLabel(journey)}</strong></td>
                      <td><Badge tone={generationSourceTone(item)}>{generationSourceLabel(item)}</Badge></td>
                      <td>{item.epic || '-'}</td>
                      <td><strong>{item.module || '-'}</strong><small>{item.component || '-'}</small></td>
                      <td>
                        {item.jira_url ? (
                          <div className="jira-story-state">
                            <a className="jira-story-link" href={item.jira_url} target="_blank" rel="noreferrer">{item.jira_key || 'Open in Jira'}</a>
                            <small>{jiraRefreshLabel(item)}</small>
                            {jiraRefreshTime(item) && <small>{jiraRefreshTime(item)}</small>}
                          </div>
                        ) : <Badge tone="neutral">Local</Badge>}
                      </td>
                      <td>
                        <button type="button" className="table-danger-button" onClick={() => deleteStory(item.story_id)} disabled={deletingStoryId === item.story_id}>
                          {deletingStoryId === item.story_id ? 'Deleting...' : 'Delete'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              />
            ) : (
              <div className="workflow-minimal-empty">
                <strong>No user stories exist for the selected journeys.</strong>
                <span>Use Generate User Stories above to create and save them.</span>
              </div>
            )}
          </div>
        ) : (
          <div className="workflow-minimal-empty workflow-minimal-start">
            <strong>Select a journey map to begin.</strong>
            <span>Its generated user stories will appear in one consolidated table.</span>
          </div>
        )}
      </div>
    </Card>
  )
}
