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

export function UserStoriesPage() {
  const { data, loading, refetch } = useFetch(api.getUserStories, [])
  const items = data?.items ?? []
  const [journeys, setJourneys] = useState([])
  const [jiraConfig, setJiraConfig] = useState(null)
  const [selectedJourneys, setSelectedJourneys] = useState([])
  const [syncing, setSyncing] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState('')
  const [journeyPickerValue, setJourneyPickerValue] = useState('')

  useEffect(() => {
    api.getJourneys().then((d) => setJourneys(d.items ?? d ?? [])).catch(() => setJourneys([]))
    api.getConfiguration().then((config) => setJiraConfig(config?.jira ?? null)).catch(() => setJiraConfig(null))
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
  const selectedStoriesByJourney = useMemo(() => {
    return selectedJourneyItems.reduce((acc, journey) => {
      acc[journey.journey_id] = storiesByJourney[journey.journey_id] ?? []
      return acc
    }, {})
  }, [selectedJourneyItems, storiesByJourney])
  const availableJourneyCount = journeys.filter((journey) => !selectedJourneySet.has(journey.journey_id)).length
  const jiraConnected = Boolean(jiraConfig?.base_url && jiraConfig?.project_key && jiraConfig?.username)

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
    setSelectedJourneys((current) => (current.includes(journeyId) ? current : [...current, journeyId]))
    setJourneyPickerValue('')
  }

  const removeSelectedJourney = (journeyId) => {
    setSelectedJourneys((current) => current.filter((id) => id !== journeyId))
    if (journeyPickerValue === journeyId) setJourneyPickerValue('')
  }

  const getJourneyLabel = (journey) => journey?.journey_title || journey?.source_url || journey?.application_url || journey?.journey_id || 'Journey map'

  const generateStories = async () => {
    setMessage('')
    if (!selectedJourneys.length) {
      setMessage('Select at least one journey map to generate user stories.')
      return
    }
    setGenerating(true)
    setSyncing(false)
    try {
      const result = await api.generateUserStories({ journey_ids: selectedJourneys })
      const generatedStories = result?.stories ?? []
      const generatedStoryIds = generatedStories.map((story) => story.story_id).filter(Boolean)

      if (jiraConnected && generatedStoryIds.length) {
        setSyncing(true)
        try {
          const syncResult = await api.syncUserStoriesToJira({ story_ids: generatedStoryIds })
          setMessage(syncResult.message || `Generated ${generatedStories.length} user stories and synced them to Jira.`)
        } catch (syncError) {
          setMessage(`${syncError?.message || 'Jira sync failed.'} Generated ${generatedStories.length} user stories and saved them locally.`)
        } finally {
          setSyncing(false)
        }
      } else {
        setMessage(`Generated ${generatedStories.length} user stories and saved them locally${jiraConnected ? '' : ' because Jira is not configured'}.`)
      }

      await refetch()
    } catch (error) {
      setMessage(error?.message || 'Unable to generate user stories.')
    } finally {
      setGenerating(false)
      setSyncing(false)
    }
  }

  return (
    <Card
      title="User Stories"
      subtitle="Generated stories mapped to discovered journeys."
      actions={<button onClick={refetch} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>}
    >
      <div className="story-command-panel">
        <div className="story-command-header">
          <div>
            <h3>Generate User Stories</h3>
            <p>Select one or more journey maps, then generate Jira-ready stories for those journeys.</p>
          </div>
          <Badge tone={selectedJourneys.length ? 'success' : 'neutral'}>{selectedJourneys.length} selected</Badge>
        </div>

        <div className="journey-dropdown-layout">
          <label className="field journey-dropdown-field">
            <span>Add Journey Maps</span>
            <select value={journeyPickerValue} onChange={addJourneyFromDropdown} disabled={!journeys.length || !availableJourneyCount}>
              <option value="">{journeys.length ? availableJourneyCount ? 'Choose a journey map and add it to selection' : 'All journey maps selected' : 'No journey maps available'}</option>
              {nestedJourneys.map((journey) => (
                <option key={journey.journey_id} value={journey.journey_id} disabled={selectedJourneySet.has(journey.journey_id)}>
                  {getJourneyLabel(journey)}
                </option>
              ))}
            </select>
          </label>
          <div className="journey-dropdown-actions">
            <button className="secondary-button" onClick={selectAllJourneys} disabled={!journeys.length}>Select All</button>
            <button className="secondary-button" onClick={clearSelection} disabled={!selectedJourneys.length}>Clear</button>
          </div>
        </div>

        <div className="selected-journey-summary">
          <div className="selected-journey-summary-head">
            <strong>Selected Journey IDs</strong>
            <span>{selectedJourneys.length ? `${selectedJourneys.length} journey map${selectedJourneys.length > 1 ? 's' : ''} ready` : 'No journey maps selected'}</span>
          </div>
          {selectedJourneyItems.length ? (
            <div className="selected-journey-chips">
              {selectedJourneyItems.map((journey) => (
                <button key={journey.journey_id} type="button" className="selected-journey-chip" onClick={() => removeSelectedJourney(journey.journey_id)} title="Remove journey">
                  <span>{journey.journey_id}</span>
                  <strong>Remove</strong>
                </button>
              ))}
            </div>
          ) : (
            <p className="selected-journey-empty">Use the dropdown above to add journey maps for story generation.</p>
          )}
        </div>

        <div className="story-command-actions workflow-primary-actions">
          <button onClick={generateStories} disabled={generating || syncing || loading || !selectedJourneys.length}>
            {syncing ? 'Generating and Syncing to Jira...' : generating ? 'Generating User Stories...' : 'Generate User Stories'}
          </button>
        </div>

        {message && <div className="notification-row"><Badge tone={message.toLowerCase().includes('unable') || message.toLowerCase().includes('failed') ? 'danger' : 'success'}>{message}</Badge></div>}
      </div>

      {selectedJourneys.length ? (
        <Card title="Generated Stories for Selected Journeys" subtitle="Only stories linked to the selected journey maps are shown here.">
          <div className="story-group-stack">
            {selectedJourneyItems.map((journey) => {
              const journeyStories = selectedStoriesByJourney[journey.journey_id] ?? []
              return (
                <section key={journey.journey_id} className="story-group">
                  <div className="story-group-head">
                    <div>
                      <h3>{getJourneyLabel(journey)}</h3>
                      <p>{journey.journey_id}</p>
                    </div>
                    <Badge tone={journeyStories.length ? 'success' : 'neutral'}>{journeyStories.length} stories</Badge>
                  </div>
                  {journeyStories.length ? (
                    <Table
                      columns={['Story ID', 'Summary', 'Epic', 'Module', 'Component']}
                      rows={journeyStories.map((item) => (
                        <tr key={item.story_id}>
                          <td>{item.story_id}</td>
                          <td>{item.summary}</td>
                          <td>{item.epic}</td>
                          <td>{item.module}</td>
                          <td><Badge tone="info">{item.component}</Badge></td>
                        </tr>
                      ))}
                    />
                  ) : (
                    <div className="story-empty-inline">
                      <strong>No stories generated for this journey yet.</strong>
                      <span>Click Generate User Stories to create stories for this selected journey map.</span>
                    </div>
                  )}
                </section>
              )
            })}
          </div>
        </Card>
      ) : (
        <EmptyState title="Select a journey map" description="Choose one or more journey maps above to view or generate user stories for only those journeys." />
      )}
    </Card>
  )
}
