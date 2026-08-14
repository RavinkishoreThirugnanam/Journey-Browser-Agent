import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Badge } from '../components/Ui'
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
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const requestedJourneyId = searchParams.get('journey') || ''
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

  useEffect(() => {
    if (!requestedJourneyId || !journeys.some((journey) => journey.journey_id === requestedJourneyId)) return
    setSelectedJourneys([requestedJourneyId])
  }, [requestedJourneyId, journeys])

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
  const latestJiraRefresh = useMemo(() => {
    const timestamps = selectedStories
      .map((story) => Date.parse(story.jira_last_refreshed_at || ''))
      .filter(Number.isFinite)
    if (!timestamps.length) return 'Not refreshed yet'
    return `Last refreshed ${new Date(Math.max(...timestamps)).toLocaleString()}`
  }, [selectedStories])
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

  const selectedJourney = selectedJourneyItems[0] || null
  const allJourneysSelected = journeys.length > 1 && selectedJourneys.length === journeys.length
  const journeySelectionValue = allJourneysSelected ? '__all__' : (selectedJourneys.length === 1 ? selectedJourneys[0] : '')
  const selectedJourneyLabel = allJourneysSelected ? 'All Journey Maps' : (selectedJourney ? getJourneyLabel(selectedJourney) : 'User Stories')

  return (
    <section className="user-stories-simple">
      <header className="user-stories-simple-header">
        <div>
          <span className="eyebrow">Stage 2 · User Stories</span>
          <h2>User Stories</h2>
          <p>Select a journey map to review or generate its user stories.</p>
        </div>
        <label className="user-stories-journey-select">
          <span>Journey map</span>
          <select
            value={journeySelectionValue}
            onChange={(event) => {
              const journeyId = event.target.value
              setSelectedJourneys(journeyId === '__all__' ? journeys.map((journey) => journey.journey_id) : (journeyId ? [journeyId] : []))
            }}
            disabled={!journeys.length}
          >
            <option value="">{journeys.length ? 'Select a journey map' : 'No journey maps available'}</option>
            {journeys.length > 1 ? <option value="__all__">Select All Journey Maps</option> : null}
            {journeys.map((journey) => <option key={journey.journey_id} value={journey.journey_id}>{getJourneyLabel(journey)}</option>)}
          </select>
        </label>
      </header>

      {message ? <div className="user-stories-message"><Badge tone={message.toLowerCase().includes('unable') || message.toLowerCase().includes('failed') ? 'danger' : 'success'}>{message}</Badge></div> : null}

      {selectedJourney ? (
        <section className="user-stories-table-section">
          <div className="user-stories-table-heading">
            <div>
              <h3>{selectedStories.length} User {selectedStories.length === 1 ? 'Story' : 'Stories'}</h3>
              <span>{selectedJourneyLabel}</span>
            </div>
            <div className="user-stories-table-actions">
              <div className="user-stories-jira-refresh">
                <button type="button" className="secondary-button utility-action" onClick={refreshStoriesFromJira} disabled={refreshingJira || !jiraLinkedSelectedStories.length} title="Fetch the latest story updates from Jira">
                  <span className={refreshingJira ? 'refresh-icon spinning' : 'refresh-icon'} aria-hidden="true">↻</span>
                  {refreshingJira ? 'Refreshing...' : 'Refresh from Jira'}
                </button>
                <small>{latestJiraRefresh}</small>
              </div>
              {!selectedStories.length ? (
                <button type="button" onClick={generateStories} disabled={generating || loading}>
                  {generating ? 'Generating...' : 'Generate User Stories'}
                </button>
              ) : null}
            </div>
          </div>
          {selectedStories.length ? (
            <div className="user-stories-table-wrap">
              <table className="user-stories-table">
                <thead><tr><th>User Story</th><th>Journey</th><th>Epic</th><th>Jira</th><th>Action</th></tr></thead>
                <tbody>
                  {selectedStories.map((item) => {
                    const storyJourney = journeys.find((journey) => journey.journey_id === item.journey_id)
                    return (
                      <tr key={item.story_id}>
                        <td><strong>{item.summary}</strong></td>
                        <td>{getJourneyLabel(storyJourney)}</td>
                        <td><span className="user-story-category">{item.epic || 'User Journey'}</span></td>
                        <td>
                          {item.jira_url ? (
                            <div className="jira-story-state">
                              <a className="jira-story-link" href={item.jira_url} target="_blank" rel="noreferrer">{item.jira_key || 'Open in Jira'}</a>
                              {jiraRefreshTime(item) ? <small>{jiraRefreshTime(item)}</small> : null}
                            </div>
                          ) : <span className="user-story-local">Local</span>}
                        </td>
                        <td>
                          <button type="button" className="user-story-delete" onClick={() => deleteStory(item.story_id)} disabled={deletingStoryId === item.story_id}>
                            {deletingStoryId === item.story_id ? 'Deleting...' : 'Delete'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="user-stories-simple-empty">No user stories yet. Generate stories for this journey map.</div>
          )}
        </section>
      ) : <div className="user-stories-simple-start">Select a journey map to display its user stories.</div>}

      <footer className="workflow-fixed-footer user-stories-fixed-footer">
        <div className="workflow-fixed-stage"><strong>Stage 2 of 5</strong><span>&bull;</span><span>{selectedJourneyLabel}</span></div>
        <div className="workflow-fixed-actions">
          <button type="button" className="secondary-button" onClick={() => navigate(selectedJourney && !allJourneysSelected ? `/journeys/${encodeURIComponent(selectedJourney.journey_id)}` : '/workflow')}>{allJourneysSelected ? 'Back to Journeys' : 'Back to Journey'}</button>
          <button
            type="button"
            onClick={() => navigate(allJourneysSelected
              ? `/tests?journeys=${encodeURIComponent(selectedJourneys.join(','))}`
              : `/tests?journey=${encodeURIComponent(selectedJourneys[0] || '')}`)}
            disabled={!selectedStories.length}
          >Continue to Test Cases <span aria-hidden="true">&rarr;</span></button>
        </div>
      </footer>
    </section>
  )
}
