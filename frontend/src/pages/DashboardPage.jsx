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

function RecentItem({ title, subtitle, badge }) {
  return (
    <div className="detail-row">
      <div>
        <strong>{title}</strong>
        <small>{subtitle}</small>
      </div>
      <Badge tone="info">{badge}</Badge>
    </div>
  )
}

export function DashboardPage() {
  const nav = useNavigate()
  const [counts, setCounts] = useState({ journeys: 0, stories: 0, cases: 0, scripts: 0 })
  const [latest, setLatest] = useState({ journeys: [], stories: [], cases: [], scripts: [] })
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let mounted = true
    Promise.all([api.getJourneys(), api.getUserStories(), api.getTestCases(), api.getTestScripts()]).then(([journeys, stories, testCases, testScripts]) => {
      if (!mounted) return
      const journeyItems = journeys.items ?? journeys ?? []
      const storyItems = stories.items ?? stories ?? []
      const caseItems = testCases.items ?? testCases ?? []
      const scriptItems = testScripts.items ?? testScripts ?? []
      setCounts({
        journeys: journeyItems.length,
        stories: storyItems.length,
        cases: caseItems.length,
        scripts: scriptItems.length,
      })
      setLatest({
        journeys: journeyItems.slice(0, 3),
        stories: storyItems.slice(0, 3),
        cases: caseItems.slice(0, 3),
        scripts: scriptItems.slice(0, 3),
      })
    }).catch(() => {
      if (mounted) setMessage('Unable to load dashboard summary.')
    }).finally(() => {
      if (mounted) setLoading(false)
    })
    return () => { mounted = false }
  }, [])

  const totals = useMemo(() => [
    { label: 'Journey IDs', value: counts.journeys, note: 'Captured from browser discovery' },
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

        <div className="grid two">
          <Card title="Current Status" subtitle="At a glance summary of the platform output.">
            <div className="metrics">
              <div><strong>Exploration</strong><span>{loading ? 'Loading...' : `${counts.journeys} journeys discovered`}</span></div>
              <div><strong>Stories</strong><span>{counts.stories} generated</span></div>
              <div><strong>Cases</strong><span>{counts.cases} generated</span></div>
              <div><strong>Scripts</strong><span>{counts.scripts} generated</span></div>
            </div>
          </Card>

          <Card title="Quick Actions" subtitle="Jump into the main workflow or configuration.">
            <div className="inline-actions">
              <button onClick={() => nav('/workflow')}>Open Workflow</button>
              <button className="secondary-button" onClick={() => nav('/configuration')}>Open Configuration</button>
              <button className="secondary-button" onClick={() => nav('/workflow')}>View Journeys</button>
            </div>
            {message && <div className="notification-row"><Badge tone="warning">{message}</Badge></div>}
          </Card>
        </div>

        <div className="grid two">
          <Card title="Recent Journeys" subtitle="Latest discovered journey IDs and entry points.">
            {latest.journeys.length ? (
              <div className="stack">
                {latest.journeys.map((journey) => (
                  <RecentItem
                    key={journey.journey_id}
                    title={journey.journey_title || journey.journey_id}
                    subtitle={journey.source_url || journey.application_url}
                    badge={`${journey.steps?.length ?? 0} steps`}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-state">No journeys captured yet.</div>
            )}
          </Card>

          <Card title="Recent Artifacts" subtitle="The most recent story, test case, and script output.">
            <div className="stack">
              <div className="detail-row">
                <span>Latest Story</span>
                <strong>{latest.stories[0]?.summary || 'No stories yet'}</strong>
              </div>
              <div className="detail-row">
                <span>Latest Case</span>
                <strong>{latest.cases[0]?.title || 'No test cases yet'}</strong>
              </div>
              <div className="detail-row">
                <span>Latest Script</span>
                <strong>{latest.scripts[0]?.script_id || 'No test scripts yet'}</strong>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
