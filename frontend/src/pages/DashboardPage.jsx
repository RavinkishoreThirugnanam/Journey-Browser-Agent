import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Badge, PageHeader } from '../components/Ui'

function targetName(value) {
  try {
    return new URL(value).hostname
  } catch {
    return value || 'No target captured'
  }
}

function capturedWhen(value) {
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return 'Recently'
  const elapsed = Math.max(0, Date.now() - timestamp)
  const hours = Math.floor(elapsed / 3600000)
  if (hours < 1) return 'Just now'
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days} days ago`
  return new Date(value).toLocaleDateString()
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
    { label: 'journeys', value: counts.journeys },
    { label: 'user stories', value: counts.stories },
    { label: 'test cases', value: counts.cases },
    { label: 'test scripts', value: counts.scripts },
  ], [counts])

  return (
    <>
      <PageHeader eyebrow="Dashboard" title="Quality Engineering Automation Overview" description="Monitor journey discovery, test design, automation assets, and the latest QA workflow results from one place." />
      <div className="dashboard-minimal">
        <section className="dashboard-minimal-grid" aria-label="Journey workspace overview">
          <section className="dashboard-minimal-panel dashboard-start-panel">
            <header><h2>Start Here</h2></header>
            <div className="dashboard-start-content">
              <p>New to this workspace? Run an exploration—point the browser agent at any URL and describe what it should discover.</p>
              <button type="button" onClick={() => nav('/workflow?create=1')}>＋&nbsp; Create a New Journey</button>
              <button type="button" className="dashboard-text-action" onClick={() => nav('/workflow')}>Browse Existing Journeys</button>
              {message && <div className="notification-row"><Badge tone="warning">{message}</Badge></div>}
            </div>
          </section>

          <section className="dashboard-minimal-panel dashboard-recent-panel">
            <header>
              <h2>Recent Journeys</h2>
              <span className="dashboard-total-pill">{counts.journeys} total</span>
            </header>
            {loading ? (
              <div className="dashboard-minimal-empty">Loading recent journeys...</div>
            ) : latestJourneys.length ? (
              <div className="dashboard-recent-table-wrap">
                <table className="dashboard-recent-table">
                  <thead><tr><th>Journey</th><th>Target</th><th>Captured</th></tr></thead>
                  <tbody>
                    {latestJourneys.map((journey) => (
                      <tr key={journey.journey_id}>
                        <td><button type="button" onClick={() => nav(`/journeys/${encodeURIComponent(journey.journey_id)}`)}>{journey.journey_title || 'Journey'}</button></td>
                        <td>{targetName(journey.source_url)}</td>
                        <td>{capturedWhen(journey.captured_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="dashboard-minimal-empty">No journeys captured yet.</div>}
          </section>
        </section>

        <section className="dashboard-workspace-totals" aria-label="Workspace totals">
          <span className="dashboard-totals-label">So Far in This Workspace</span>
          <div className="dashboard-total-rail">
            {totals.map((stat) => (
              <div className="dashboard-total-item" key={stat.label}>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}
