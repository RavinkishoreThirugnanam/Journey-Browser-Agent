import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Badge, Card, PageHeader } from '../components/Ui'

function Stat({ label, value, note }) {
  return (
    <div className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  )
}

function RecentItem({ title, subtitle, badge, onClick }) {
  return (
    <button type="button" className="detail-row recent-journey-button" onClick={onClick} aria-label={`Open journey details for ${title}`}>
      <div>
        <strong>{title}</strong>
        <small>{subtitle}</small>
      </div>
      <Badge tone="info">{badge}</Badge>
    </button>
  )
}

export function DashboardPage() {
  const nav = useNavigate()
  const [counts, setCounts] = useState({ journeys: 0, stories: 0, cases: 0, scripts: 0 })
  const [latestJourneys, setLatestJourneys] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let mounted = true
    let requestSequence = 0

    const loadDashboard = async () => {
      const requestId = ++requestSequence
      setLoading(true)
      try {
        const payload = await api.getDashboardSummary()
        if (!mounted || requestId !== requestSequence) return
        setCounts({
          journeys: payload?.counts?.journeys ?? 0,
          stories: payload?.counts?.stories ?? 0,
          cases: payload?.counts?.cases ?? 0,
          scripts: payload?.counts?.scripts ?? 0,
        })
        setLatestJourneys(payload?.latest?.journeys ?? [])
        setMessage('')
      } catch (error) {
        if (!mounted || requestId !== requestSequence) return
        setMessage('Unable to load dashboard summary from the Browser Agent backend.')
      } finally {
        if (mounted && requestId === requestSequence) setLoading(false)
      }
    }

    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') loadDashboard()
    }

    loadDashboard()
    window.addEventListener('focus', loadDashboard)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      mounted = false
      requestSequence += 1
      window.removeEventListener('focus', loadDashboard)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [])

  const totals = useMemo(() => [
    { label: 'Journeys', value: counts.journeys, note: 'Captured from browser discovery' },
    { label: 'User Stories', value: counts.stories, note: 'Ready for Jira sync' },
    { label: 'Test Cases', value: counts.cases, note: 'Generated from stories' },
    { label: 'Test Scripts', value: counts.scripts, note: 'Feature + JS artifacts' },
  ], [counts])

  return (
    <>
      <PageHeader eyebrow="Dashboard" title="Journey AI Summary Center" description="Monitor the latest pipeline output, summary counts, and quick actions from one place." />
      <div className="dashboard-grid">
        <div className="hero-stat-grid">
          {totals.map((stat) => <Stat key={stat.label} {...stat} />)}
        </div>

        <div className="grid dashboard-primary-grid">
          <Card title="Quick Actions" subtitle="Open the journey workflow, review previous journeys, or manage application configuration.">
            <div className="inline-actions">
              <button onClick={() => nav('/workflow')}>Open Workflow</button>
              <button className="secondary-button" onClick={() => nav('/journeys')}>View Previous Journeys</button>
              <button className="secondary-button" onClick={() => nav('/configuration')}>Open Configuration</button>
            </div>
            {message && <div className="notification-row"><Badge tone="warning">{message}</Badge></div>}
          </Card>

          <Card title="Recent Journeys" subtitle="Latest discovered journeys and entry points.">
            {loading ? (
              <div className="empty-state">Loading recent journeys...</div>
            ) : latestJourneys.length ? (
              <div className="stack">
                {latestJourneys.map((journey) => (
                  <RecentItem
                    key={journey.journey_id}
                    title={journey.journey_title || 'Journey'}
                    subtitle={journey.source_url || 'No source URL captured'}
                    badge={(journey.step_count ?? 0) + ' steps'}
                    onClick={() => nav(`/journeys?journey=${encodeURIComponent(journey.journey_id)}`)}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-state">No journeys captured yet.</div>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
