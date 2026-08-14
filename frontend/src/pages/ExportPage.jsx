import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Card } from '../components/Ui'

const exportOptions = [
  {
    type: 'user-stories',
    countKey: 'user-stories',
    title: 'User Stories',
    description: 'Requirements generated from the selected journey map in CSV format.',
    format: 'CSV',
    action: 'Export User Stories CSV',
  },
  {
    type: 'test-cases',
    countKey: 'test-cases',
    title: 'Test Cases',
    description: 'Test scenarios linked to the selected journey and stories in CSV format.',
    format: 'CSV',
    action: 'Export Test Cases CSV',
  },
  {
    type: 'test-scripts',
    countKey: 'test-scripts',
    title: 'Test Scripts',
    description: 'Generated Gherkin feature files and JavaScript automation files in one ZIP.',
    format: 'FEATURE + JS',
    action: 'Export Feature + JS Files',
  },
  {
    type: 'complete-package',
    countKey: null,
    title: 'Complete Package',
    description: 'Journey map, user stories, test cases, and scripts in an Excel workbook.',
    format: 'EXCEL',
    action: 'Export Complete Excel Package',
    primary: true,
  },
]

export function ExportPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const requestedIds = (searchParams.get('journeys') || '').split(',').filter(Boolean)
  const requestedId = searchParams.get('journey') || ''
  const [journeys, setJourneys] = useState([])
  const [selectedJourneyIds, setSelectedJourneyIds] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getJourneys()
      .then((result) => {
        const items = result?.items ?? result ?? []
        setJourneys(items)
        const availableIds = new Set(items.map((journey) => journey.journey_id))
        const contextIds = (requestedIds.length ? requestedIds : (requestedId ? [requestedId] : []))
          .filter((journeyId) => availableIds.has(journeyId))
        setSelectedJourneyIds(contextIds.length ? contextIds : items.map((journey) => journey.journey_id))
      })
      .catch(() => {
        setJourneys([])
        setSelectedJourneyIds([])
        setError('Unable to load journey maps.')
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!selectedJourneyIds.length) {
      setSummary(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    api.exportArtifact('complete-package', selectedJourneyIds)
      .then(setSummary)
      .catch((requestError) => setError(requestError?.message || 'Unable to load current export outputs.'))
      .finally(() => setLoading(false))
  }, [selectedJourneyIds])

  const allSelected = journeys.length > 1 && selectedJourneyIds.length === journeys.length
  const selectionValue = allSelected ? '__all__' : (selectedJourneyIds.length === 1 ? selectedJourneyIds[0] : '')
  const selectedJourneys = useMemo(
    () => journeys.filter((journey) => selectedJourneyIds.includes(journey.journey_id)),
    [journeys, selectedJourneyIds],
  )
  const selectionLabel = allSelected
    ? `All Journey Maps (${selectedJourneyIds.length})`
    : (selectedJourneys[0]?.journey_title || selectedJourneys[0]?.starting_point || 'Select a journey map')
  const counts = summary?.counts || {}

  const selectJourney = (event) => {
    const value = event.target.value
    setSelectedJourneyIds(value === '__all__' ? journeys.map((journey) => journey.journey_id) : (value ? [value] : []))
  }

  return (
    <Card className="export-page-with-footer export-simple-page" title="Review & Export" subtitle="Download the current QA outputs for a selected journey map.">
      <div className="export-simple-selector">
        <label>
          <span>Journey map</span>
          <select value={selectionValue} onChange={selectJourney} disabled={!journeys.length}>
            <option value="">{journeys.length ? 'Select a journey map' : 'No journey maps available'}</option>
            {journeys.length > 1 ? <option value="__all__">Select All Journey Maps</option> : null}
            {journeys.map((journey) => (
              <option key={journey.journey_id} value={journey.journey_id}>
                {journey.journey_title || journey.starting_point || journey.starting_url || 'Journey map'}
              </option>
            ))}
          </select>
        </label>
        <div className="export-simple-context">
          <span aria-hidden="true">&#10003;</span>
          <strong>{selectionLabel}</strong>
          <small>{loading ? 'Checking current outputs...' : 'Current saved outputs only'}</small>
        </div>
      </div>

      {error ? <p className="export-simple-error" role="alert">{error}</p> : null}

      <div className="export-simple-grid">
        {exportOptions.map((option) => {
          const count = option.countKey ? Number(counts[option.countKey] || 0) : null
          const disabled = loading || !selectedJourneyIds.length || (option.countKey && count === 0)
          return (
            <section key={option.type} className={`export-option${option.primary ? ' primary' : ''}`}>
              <div className="export-option-heading">
                <div>
                  <h3>{option.title}</h3>
                  <p>{option.description}</p>
                </div>
                <span>{option.primary ? option.format : `${count} ready · ${option.format}`}</span>
              </div>
              <button type="button" className={option.primary ? '' : 'secondary-button'} disabled={disabled} onClick={() => api.downloadArtifact(option.type, selectedJourneyIds)}>
                <span aria-hidden="true">&#8595;</span> {option.action}
              </button>
            </section>
          )
        })}
      </div>

      <footer className="workflow-fixed-footer export-fixed-footer">
        <div className="workflow-fixed-stage"><strong>Stage 5 of 5</strong><span>&bull;</span><span>Review &amp; Export</span></div>
        <div className="workflow-fixed-actions">
          <button type="button" className="secondary-button" onClick={() => navigate(selectedJourneyIds.length === 1 ? `/scripts?journey=${encodeURIComponent(selectedJourneyIds[0])}` : '/scripts')}>Back to Test Scripts</button>
        </div>
      </footer>
    </Card>
  )
}
