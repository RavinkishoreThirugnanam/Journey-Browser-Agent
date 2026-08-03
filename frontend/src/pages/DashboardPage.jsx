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

function toItems(payload) {
  return Array.isArray(payload?.items) ? payload.items : Array.isArray(payload) ? payload : []
}

function freshnessValue(item, index) {
  const candidates = [
    item?.generated_at,
    item?.updated_at,
    item?.created_at,
    item?.timestamp,
    item?.exploration_metadata?.exploration_timestamp,
  ]
  for (const value of candidates) {
    const parsed = Date.parse(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return index
}

function newest(items, limit = 3) {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => freshnessValue(b.item, b.index) - freshnessValue(a.item, a.index))
    .slice(0, limit)
    .map(({ item }) => item)
}

function artifactTitle(item, fallback) {
  return item?.summary || item?.title || item?.feature_filename || item?.script_id || fallback
}

export function DashboardPage() {
  const nav = useNavigate()
  const [counts, setCounts] = useState({ journeys: 0, stories: 0, cases: 0, scripts: 0 })
  const [latest, setLatest] = useState({ journeys: [], stories: [], cases: [], scripts: [] })
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let mounted = true

    const loadDashboard = () => {
      setLoading(true)
      Promise.all([api.getJourneys(), api.getUserStories(), api.getTestCases(), api.getTestScripts()]).then(([journeys, stories, testCases, testScripts]) => {
        if (!mounted) return
        const journeyItems = toItems(journeys)
        const journeyIds = new Set(journeyItems.map((journey) => journey.journey_id).filter(Boolean))
        const rawStoryItems = toItems(stories)
        const storyItems = rawStoryItems.filter((story) => story.journey_id && journeyIds.has(story.journey_id))
        const storyIds = new Set(storyItems.map((story) => story.story_id).filter(Boolean))
        const rawCaseItems = toItems(testCases)
        const caseItems = rawCaseItems.filter((testCase) => {
          const journeyMatch = testCase.journey_id && journeyIds.has(testCase.journey_id)
          const storyMatch = testCase.user_story_id && storyIds.has(testCase.user_story_id)
          return journeyMatch || storyMatch
        })
        const caseIds = new Set(caseItems.map((testCase) => testCase.test_case_id).filter(Boolean))
        const rawScriptItems = toItems(testScripts)
        const scriptItems = rawScriptItems.filter((script) => {
          const journeyMatch = script.journey_id && journeyIds.has(script.journey_id)
          const storyMatch = script.user_story_id && storyIds.has(script.user_story_id)
          const caseMatch = script.test_case_id && caseIds.has(script.test_case_id)
          return journeyMatch || storyMatch || caseMatch
        })
        setCounts({
          journeys: journeyItems.length,
          stories: storyItems.length,
          cases: caseItems.length,
          scripts: scriptItems.length,
        })
        setLatest({
          journeys: newest(journeyItems),
          stories: newest(storyItems),
          cases: newest(caseItems),
          scripts: newest(scriptItems),
        })
        setMessage('')
      }).catch(() => {
        if (mounted) setMessage('Unable to load dashboard summary.')
      }).finally(() => {
        if (mounted) setLoading(false)
      })
    }

    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') loadDashboard()
    }

    loadDashboard()
    window.addEventListener('focus', loadDashboard)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      mounted = false
      window.removeEventListener('focus', loadDashboard)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
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
                    subtitle={journey.source_url || journey.application_url || journey.app_url || 'No source URL captured'}
                    badge={`${journey.steps?.length ?? 0} steps`}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-state">No journeys captured yet.</div>
            )}
          </Card>

          <Card title="Recent Artifacts" subtitle="The newest story, test case, and script output from current storage.">
            <div className="stack">
              <div className="detail-row">
                <span>Latest Story</span>
                <strong>{artifactTitle(latest.stories[0], 'No stories yet')}</strong>
              </div>
              <div className="detail-row">
                <span>Latest Case</span>
                <strong>{artifactTitle(latest.cases[0], 'No test cases yet')}</strong>
              </div>
              <div className="detail-row">
                <span>Latest Script</span>
                <strong>{artifactTitle(latest.scripts[0], 'No test scripts yet')}</strong>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}