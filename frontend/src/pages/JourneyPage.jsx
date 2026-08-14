import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Badge, Card, Table } from '../components/Ui'
import { renderMermaid } from '../utils/mermaid'

function DetailRow({ label, value }) {
  return (
    <div className="detail-row">
      <span>{label}</span>
      <strong>{value || '-'}</strong>
    </div>
  )
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return String(value)
  if (typeof value === 'object') return JSON.stringify(value)
  return value
}

function cleanEvidenceText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function uniqueEvidenceItems(items, limit = 24) {
  const seen = new Set()
  return items.filter((item) => {
    const value = cleanEvidenceText(item)
    const key = value.toLowerCase()
    if (!value || value === '-' || seen.has(key)) return false
    seen.add(key)
    return true
  }).slice(0, limit)
}

function extractDomPageEvidence(html) {
  if (!html || typeof DOMParser === 'undefined') return { title: '', primaryHeading: '', headings: [], descriptions: [], cards: [], ctas: [] }
  try {
    const documentNode = new DOMParser().parseFromString(html, 'text/html')
    const textOf = (element) => cleanEvidenceText(element?.textContent)
    const isNavigationChrome = (element) => Boolean(
      element?.matches?.('[role="menuitem"]') ||
      element?.closest?.('header, nav, footer, [role="navigation"], [role="menu"], [role="menubar"]'),
    )
    const isSnapshotHidden = (element) => Boolean(
      element?.hidden ||
      element?.getAttribute?.('aria-hidden') === 'true' ||
      /display\s*:\s*none|visibility\s*:\s*hidden/i.test(element?.getAttribute?.('style') || ''),
    )
    const headingElements = Array.from(documentNode.querySelectorAll('h1, h2, h3, [role="heading"]'))
      .filter((element) => !isNavigationChrome(element) && !isSnapshotHidden(element) && textOf(element))
    const headings = uniqueEvidenceItems(
      headingElements.map(textOf),
      100,
    )
    const primaryHeadingNode = headingElements.find((element) => element.matches('main h1, [role="main"] h1, article h1'))
      || headingElements.find((element) => element.matches('h1'))
      || headingElements[0]
    const primaryHeading = textOf(primaryHeadingNode)
    const title = textOf(documentNode.querySelector('title'))
    const descriptions = uniqueEvidenceItems(
      Array.from(documentNode.querySelectorAll('main p, article p, [class*="description"]')).map(textOf).filter((text) => text.length >= 30),
      100,
    )
    const cards = []
    const cardNodes = documentNode.querySelectorAll('article, [class*="card"], [data-testid*="card"], [data-test*="card"]')
    Array.from(cardNodes).slice(0, 500).forEach((card) => {
      const title = textOf(card.querySelector('h2, h3, h4, [class*="title"], strong'))
      const description = textOf(card.querySelector('p, [class*="description"], [class*="summary"]'))
      const ctaNode = card.querySelector('a, button, [role="button"]')
      const cta = textOf(ctaNode)
      const image = card.querySelector('img')
      const imageUrl = cleanEvidenceText(image?.getAttribute('src') || image?.getAttribute('data-src') || image?.getAttribute('data-lazy-src'))
      const imageAlt = cleanEvidenceText(image?.getAttribute('alt'))
      const destinationUrl = cleanEvidenceText(ctaNode?.getAttribute('href') || card.querySelector('a[href]')?.getAttribute('href'))
      if (title && title.length <= 220) cards.push({ title, description, cta, imageUrl, imageAlt, destinationUrl })
    })
    const uniqueCards = []
    const cardKeys = new Set()
    cards.forEach((card) => {
      const key = `${card.title}|${card.description}`.toLowerCase()
      if (!cardKeys.has(key)) {
        cardKeys.add(key)
        uniqueCards.push(card)
      }
    })
    const ctas = uniqueEvidenceItems(
      Array.from(documentNode.querySelectorAll('main a, main button, [role="main"] a, [role="main"] button')).map(textOf),
      200,
    )
    return { title, primaryHeading, headings, descriptions, cards: uniqueCards.slice(0, 200), ctas }
  } catch {
    return { title: '', primaryHeading: '', headings: [], descriptions: [], cards: [], ctas: [] }
  }
}

function buildPageEvidence(steps) {
  const pages = new Map()
  steps.forEach((step, stepIndex) => {
    const pageUrl = cleanEvidenceText(step.page_url) || `captured-page-${stepIndex + 1}`
    if (!pages.has(pageUrl)) {
      pages.set(pageUrl, {
        url: pageUrl,
        title: cleanEvidenceText(step.page_title) || 'Untitled page',
        stepNumbers: [],
        interactions: [],
        headings: [],
        descriptions: [],
        cards: [],
        ctas: [],
        screenshots: [],
        domSnapshotCount: 0,
      })
    }
    const page = pages.get(pageUrl)
    page.stepNumbers.push(step.step_number ?? stepIndex + 1)
    if ((!page.title || page.title === 'Untitled page') && step.page_title) page.title = cleanEvidenceText(step.page_title)
    const interactions = Array.isArray(step.interactions) ? step.interactions.filter(Boolean) : []
    interactions.forEach((interaction) => {
      page.interactions.push(interaction)
      const label = cleanEvidenceText(interaction.element_label)
      const type = cleanEvidenceText(interaction.element_type).toLowerCase()
      if (label && ['heading', 'h1', 'h2', 'h3', 'title'].includes(type)) page.headings.push(label)
      if (label && ['card', 'article', 'tile'].includes(type)) page.cards.push({ title: label, description: cleanEvidenceText(interaction.value), cta: '' })
      if (label && ['a', 'link', 'button', 'menuitem'].includes(type)) page.ctas.push(label)
      const visibleElements = Array.isArray(interaction.visible_elements) ? interaction.visible_elements : []
      visibleElements.forEach((item) => {
        const visibleLabel = cleanEvidenceText(item?.label || item?.text || item?.name)
        const visibleType = cleanEvidenceText(item?.type).toLowerCase()
        if (!visibleLabel) return
        if (/heading|title/.test(visibleType)) page.headings.push(visibleLabel)
        else if (/card|article|tile/.test(visibleType)) page.cards.push({ title: visibleLabel, description: '', cta: '' })
        else if (/link|button|cta/.test(visibleType)) page.ctas.push(visibleLabel)
      })
      const domHtml = interaction.dom_snapshot_after || interaction.dom_snapshot_before || ''
      if (domHtml) {
        page.domSnapshotCount += 1
        const domEvidence = extractDomPageEvidence(domHtml)
        const meaningfulTitle = domEvidence.primaryHeading || domEvidence.title
        if (meaningfulTitle) page.title = meaningfulTitle
        page.headings.push(...domEvidence.headings)
        page.descriptions.push(...domEvidence.descriptions)
        page.cards.push(...domEvidence.cards)
        page.ctas.push(...domEvidence.ctas)
      }
      if (interaction.screenshot_before) page.screenshots.push(interaction.screenshot_before)
      if (interaction.screenshot_after) page.screenshots.push(interaction.screenshot_after)
    })
  })
  return Array.from(pages.values()).map((page) => {
    const cardKeys = new Set()
    const cards = page.cards.filter((card) => {
      const title = cleanEvidenceText(card?.title)
      const description = cleanEvidenceText(card?.description)
      const key = `${title}|${description}`.toLowerCase()
      if (!title || cardKeys.has(key)) return false
      cardKeys.add(key)
      return true
    }).slice(0, 200)
    return {
      ...page,
      stepNumbers: [...new Set(page.stepNumbers)],
      headings: uniqueEvidenceItems(page.headings, 100),
      descriptions: uniqueEvidenceItems(page.descriptions, 100),
      cards,
      ctas: uniqueEvidenceItems(page.ctas, 200),
      screenshots: uniqueEvidenceItems(page.screenshots, 50),
    }
  })
}
function interactionToLiveEvent(interaction, step, index) {
  const statusByAction = {
    open: 'Loaded',
    click: interaction.element_state_after === 'error' ? 'Failed' : 'Clicked',
    inspect: 'Observed',
    fill: 'Filled',
    select: 'Selected',
    scroll: 'Scrolled',
  }
  return {
    timestamp: interaction.event_timestamp || index,
    sequence: interaction.sequence_id ?? interaction.interaction_number ?? index + 1,
    recorded_action: interaction.action || 'inspect',
    type: `persisted_${interaction.action || 'interaction'}`,
    status: statusByAction[interaction.action] || 'Captured evidence',
    url: interaction.page_url || step.page_url,
    title: step.page_title,
    element: interaction.element_label || interaction.element_type,
    tag: interaction.element_type,
    role: interaction.role,
    selector: interaction.selector,
    destination_url: interaction.destination_url,
    result: interaction.resulted_in,
    coordinates: interaction.coordinates,
    network_count: interaction.network_events?.length ?? 0,
    screenshot_after: interaction.screenshot_after,
    dom_snapshot_captured: Boolean(interaction.dom_snapshot_before || interaction.dom_snapshot_after),
    replay_selector: interaction.replay?.selector,
  }
}

function chronologicalJourneyInteractions(steps) {
  const captured = []
  steps.forEach((step, stepIndex) => {
    const interactions = Array.isArray(step?.interactions) ? step.interactions : []
    interactions.filter(Boolean).forEach((interaction, interactionIndex) => {
      captured.push({ interaction, step, sourceOrder: (stepIndex * 100000) + interactionIndex })
    })
  })
  return captured.sort((left, right) => {
    const leftSequence = Number(left.interaction.sequence_id ?? left.interaction.interaction_number)
    const rightSequence = Number(right.interaction.sequence_id ?? right.interaction.interaction_number)
    if (Number.isFinite(leftSequence) && Number.isFinite(rightSequence) && leftSequence !== rightSequence) {
      return leftSequence - rightSequence
    }
    const leftTime = Date.parse(left.interaction.event_timestamp || '')
    const rightTime = Date.parse(right.interaction.event_timestamp || '')
    if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) return leftTime - rightTime
    return left.sourceOrder - right.sourceOrder
  })
}
const detailTabs = [
  { id: 'live-browser', label: 'Live Browser' },
  { id: 'journey-detail', label: 'Summary' },
  { id: 'visualization', label: 'Flowchart' },
  { id: 'flow-details', label: 'Page Evidence' },
]

function formatActivityTime(value) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '--:--:--'
  return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export function JourneyPage({ refreshKey = 0, initialSelectedId = '', showJourneyList = true, onCreateJourney = null } = {}) {
  const navigate = useNavigate()
  const { journeyId: routeJourneyId = '' } = useParams()
  const [data, setData] = useState([])
  const [selected, setSelected] = useState('')
  const [selectedForDelete, setSelectedForDelete] = useState([])
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [vizJourneyId, setVizJourneyId] = useState('')
  const [mermaidText, setMermaidText] = useState('')
  const [svg, setSvg] = useState('')
  const [vizLoading, setVizLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('visualization')
  const [liveStatus, setLiveStatus] = useState('')
  const [liveEvents, setLiveEvents] = useState([])
  const [replayEvents, setReplayEvents] = useState([])
  const [replayIndex, setReplayIndex] = useState(-1)
  const [replayPlaying, setReplayPlaying] = useState(false)
  const [openEvidencePages, setOpenEvidencePages] = useState({})
  const [evidenceJourneyId, setEvidenceJourneyId] = useState('')
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [manageMode, setManageMode] = useState(false)
  const detailRef = useRef(null)
  const liveTimelineRef = useRef(null)
  const selectedRef = useRef('')
  const vizRequestRef = useRef(0)
  const replayStartedRef = useRef('')

  const load = async () => {
    setLoading(true)
    try {
      const response = await api.getJourneys()
      const journeys = response.items ?? response ?? []
      setData(journeys)
      const availableIds = new Set(journeys.map((journey) => journey.journey_id))
      setSelectedForDelete((current) => current.filter((journeyId) => availableIds.has(journeyId)))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [refreshKey])

  useEffect(() => {
    selectedRef.current = selected
    setVizJourneyId(selected)
    setMermaidText('')
    setSvg('')
    setLiveEvents([])
    setReplayEvents([])
    setReplayIndex(-1)
    setReplayPlaying(false)
    setLiveStatus('')
    setEvidenceJourneyId('')
    setEvidenceLoading(false)
    replayStartedRef.current = ''
    vizRequestRef.current += 1
  }, [selected])

  useEffect(() => {
    if (!detail || activeTab !== 'visualization' || !selected || vizLoading) return
    if (vizJourneyId === selected && svg) return
    generateVisualization({ preventDefault: () => {} }, selected)
  }, [activeTab, detail?.journey_id, selected, vizJourneyId, svg, vizLoading])

  useEffect(() => {
    const requestedId = routeJourneyId || initialSelectedId
    if (requestedId) setSelected(requestedId)
  }, [initialSelectedId, routeJourneyId])

  useEffect(() => {
    if (showJourneyList) {
      setDetail(null)
      return
    }
    if (!selected) {
      setDetail(null)
      return
    }
    api.getJourney(selected, false).then((result) => {
      if (selectedRef.current !== selected) return
      setDetail(result)
      setActiveTab(showJourneyList ? 'journey-detail' : 'visualization')
      requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView({ behavior: 'auto', block: 'start' })
      })
    }).catch(() => {
      if (selectedRef.current === selected) setDetail(null)
    })
  }, [selected, showJourneyList])

  useEffect(() => {
    if (activeTab !== 'flow-details' || !selected || evidenceJourneyId === selected || evidenceLoading) return
    setEvidenceLoading(true)
    api.getJourney(selected, true).then((result) => {
      if (selectedRef.current !== selected) return
      setDetail(result)
      setEvidenceJourneyId(selected)
    }).catch(() => {
      if (selectedRef.current === selected) setMessage('Unable to load the complete page evidence package.')
    }).finally(() => {
      if (selectedRef.current === selected) setEvidenceLoading(false)
    })
  }, [activeTab, selected, evidenceJourneyId])

  useEffect(() => {
    if (activeTab !== 'live-browser' || !detail) return
    setLiveStatus('Connecting to the live browser...')
  }, [activeTab, detail?.journey_id])
  useEffect(() => {
    if (activeTab !== 'live-browser' || !detail) return
    const url = detail.starting_url || detail.source_url || detail.application_url
    const streamKey = detail.test_hints?.live_stream_key || url
    if (!url || !streamKey) return
    let cancelled = false
    const source = new EventSource(api.liveEventsUrl(streamKey))
    source.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data)
        setLiveEvents((current) => [...current, next].slice(-300))
        if (next.status) setLiveStatus(next.status)
      } catch {
        // Ignore malformed keep-alive payloads.
      }
    }
    source.onerror = () => source.close()
    // Opening the tab does not navigate the live browser directly. If a run
    // exists, the replay effect below starts it from the recorded first event.
    // Empty journeys still initialize the live browser at the base URL.
    const hasPersistedRun = Array.isArray(detail.steps) && detail.steps.some((step) => Array.isArray(step?.interactions) && step.interactions.length)
    if (!hasPersistedRun && !liveEvents.length) {
      api.navigateLiveBrowser({ url }).then((result) => {
        if (!cancelled) setLiveStatus(result.title || 'Base page loaded')
      }).catch((error) => {
        if (!cancelled) setLiveStatus('Live browser unavailable: ' + (error.message || 'navigation failed'))
      })
    } else {
      setLiveStatus('Recorded run found. Starting replay from the first event...')
    }
    return () => { cancelled = true; source.close() }
  }, [activeTab, detail?.journey_id])
  const generateVisualization = async (e, journeyIdOverride = '') => {
    e?.preventDefault?.()
    const targetJourneyId = journeyIdOverride || selected || vizJourneyId
    if (!targetJourneyId) {
      setMessage('Select a journey to visualize.')
      return
    }
    const requestId = ++vizRequestRef.current
    setVizLoading(true)
    setMessage('')
    setSvg('')
    setMermaidText('')
    try {
      const result = await api.visualizeJourney({ journey_id: targetJourneyId })
      const svgMarkup = await renderMermaid(`journey-viz-${targetJourneyId}-${Date.now()}`, result.mermaid)
      if (requestId !== vizRequestRef.current || selectedRef.current !== targetJourneyId) return
      setVizJourneyId(targetJourneyId)
      setMermaidText(result.mermaid)
      setSvg(svgMarkup)
      setActiveTab('visualization')
      requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    } catch {
      setMessage('Unable to generate the visual representation.')
    } finally {
      if (requestId === vizRequestRef.current) setVizLoading(false)
    }
  }

  const handleRowDelete = async (journeyId) => {
    setMessage('')
    const confirmed = window.confirm('Delete this journey discovery? This cannot be undone.')
    if (!confirmed) return
    try {
      await api.deleteJourney(journeyId)
      setSelectedForDelete((current) => current.filter((id) => id !== journeyId))
      if (selected === journeyId) {
        setSelected('')
        setDetail(null)
      }
      await load()
      setMessage('Journey deleted successfully.')
    } catch {
      setMessage('Unable to delete the selected journey.')
    }
  }

  const toggleJourneyForDelete = (journeyId) => {
    setSelectedForDelete((current) => (
      current.includes(journeyId)
        ? current.filter((id) => id !== journeyId)
        : [...current, journeyId]
    ))
  }

  const toggleAllJourneysForDelete = () => {
    setSelectedForDelete((current) => (
      current.length === data.length ? [] : data.map((journey) => journey.journey_id)
    ))
  }

  const deleteSelectedJourneys = async () => {
    if (!selectedForDelete.length) return
    setMessage('')
    const count = selectedForDelete.length
    const confirmed = window.confirm(`Delete ${count} selected journey ${count === 1 ? 'discovery' : 'discoveries'}? This cannot be undone.`)
    if (!confirmed) return
    try {
      const deletingIds = [...selectedForDelete]
      const result = await api.deleteJourneys(deletingIds)
      if (deletingIds.includes(selected)) {
        setSelected('')
        setDetail(null)
      }
      setSelectedForDelete([])
      await load()
      setMessage(`${result.deleted_count ?? count} selected journey ${count === 1 ? 'discovery' : 'discoveries'} deleted successfully.`)
    } catch {
      setMessage('Unable to delete the selected journey discoveries.')
    }
  }

  const deleteJourneys = async () => {
    setMessage('')
    const confirmed = window.confirm('Delete all journey discoveries? This cannot be undone.')
    if (!confirmed) return
    try {
      await api.resetJourneys()
      setSelected('')
      setSelectedForDelete([])
      setDetail(null)
      await load()
      setMessage('Journey discoveries deleted successfully.')
    } catch {
      setMessage('Unable to delete journey discoveries.')
    }
  }

  // Keep all derived journey/live state behind defensive defaults. Details are
  // loaded asynchronously and older stored journeys can contain sparse steps.
  const steps = Array.isArray(detail?.steps) ? detail.steps.filter(Boolean) : []
  const metadata = detail?.exploration_metadata ?? detail?.explorationMetadata ?? {
    app_url: detail?.app_url ?? detail?.starting_url ?? detail?.source_url ?? '',
    starting_feature: detail?.starting_feature ?? detail?.starting_point ?? '',
    task_input: detail?.task_input ?? '',
    browser: detail?.browser ?? 'chromium',
    viewport: detail?.viewport ?? {},
    is_pre_login_scoped: detail?.is_pre_login_scoped ?? false,
    total_journeys_discovered: detail?.total_journeys_discovered ?? 0,
    exploration_timestamp: detail?.exploration_timestamp ?? '',
  }

  const rawUiElements = Array.isArray(detail?.page_url_ui_element_section?.ui_elements_data)
    ? detail.page_url_ui_element_section.ui_elements_data
    : (Array.isArray(detail?.ui_elements_data) ? detail.ui_elements_data : [])
  const uiElements = rawUiElements.length ? rawUiElements : steps.map((step) => ({
    page_url: step.page_url,
    source_file: null,
    is_login_flow_context: Boolean((Array.isArray(step.interactions) ? step.interactions : []).filter(Boolean).some((interaction) => interaction.iframe_context || /login/i.test(interaction.parent_component || ''))),
    extracted_url_ui_elements: { page: { total_elements: Array.isArray(step.interactions) ? step.interactions.length : 0, elements: Array.isArray(step.interactions) ? step.interactions : [] } },
  }))
  const browserJourneys = detail?.browser_agent_section?.browser_agent_data?.journeys?.length
    ? detail.browser_agent_section.browser_agent_data.journeys
    : (detail ? [{ journey_id: detail.journey_id, steps }] : [])
  const selectedJourney = data.find((item) => item.journey_id === selected) || null
  const pageEvidence = useMemo(() => buildPageEvidence(steps), [detail?.steps])
  const chronologicalInteractions = useMemo(() => chronologicalJourneyInteractions(steps), [detail?.steps])
  const persistedLiveEvents = useMemo(() => chronologicalInteractions.map(({ interaction, step }, index) => (
    interactionToLiveEvent(interaction, step, index)
  )), [chronologicalInteractions])
  const replayInteractions = useMemo(() => chronologicalInteractions.map(({ interaction, step }) => ({
        action: interaction.action || 'inspect',
        element: interaction.element_label || interaction.element_type || '',
        element_id: interaction.element_id || '',
        selector: interaction.selector || '',
        replay_selector: interaction.replay?.selector || interaction.selector || '',
        value: interaction.value || '',
        page_url: interaction.page_url || step.page_url || '',
        destination_url: interaction.destination_url || '',
        coordinates: interaction.coordinates || {},
      })), [chronologicalInteractions])
  const liveActivityEvents = useMemo(() => {
    const merged = [
      ...(Array.isArray(persistedLiveEvents) ? persistedLiveEvents : []),
      ...(Array.isArray(liveEvents) ? liveEvents : []),
    ].filter(Boolean)
    const unique = merged.filter((event, index, all) => {
      const key = [event.type, event.timestamp, event.sequence || index, event.url, event.element].join('|')
      return all.findIndex((candidate, candidateIndex) => [candidate.type, candidate.timestamp, candidate.sequence || candidateIndex, candidate.url, candidate.element].join('|') === key) === index
    })
    return unique.sort((left, right) => {
      const leftSequence = Number(left.sequence)
      const rightSequence = Number(right.sequence)
      if (Number.isFinite(leftSequence) && Number.isFinite(rightSequence) && leftSequence !== rightSequence) return leftSequence - rightSequence
      const leftTime = Date.parse(left.timestamp) || Number(left.timestamp) || 0
      const rightTime = Date.parse(right.timestamp) || Number(right.timestamp) || 0
      return leftTime - rightTime
    })
  }, [persistedLiveEvents, liveEvents])
  const latestLiveEvent = liveActivityEvents[liveActivityEvents.length - 1] || null
  const lastClickEvent = [...liveActivityEvents].reverse().find((event) => event.type === 'click_started' || event.type === 'click_completed' || event.type === 'clicking' || event.type === 'persisted_click') || null
  const lastScanEvent = [...liveActivityEvents].reverse().find((event) => event.type === 'page_scanned' || event.type === 'persisted_inspect') || null
  const lastTargetEvent = [...liveActivityEvents].reverse().find((event) => event.type === 'target_selected') || null
  const liveEventTone = (event) => {
    const status = String(event?.status || '').toLowerCase()
    if (status.includes('failed') || status.includes('unavailable')) return 'danger'
    if (status.includes('completed') || status.includes('loaded') || status.includes('navigated')) return 'success'
    if (status.includes('click') || status.includes('target') || status.includes('planning') || status.includes('waiting')) return 'warning'
    return 'info'
  }

  useEffect(() => {
    if (!replayPlaying || replayIndex < 0 || replayIndex >= replayEvents.length) return undefined
    const timer = window.setTimeout(() => {
      if (replayIndex >= replayEvents.length - 1) {
        setReplayPlaying(false)
        setLiveStatus('Recorded replay complete.')
      } else {
        setReplayIndex((index) => index + 1)
      }
    }, 900)
    return () => window.clearTimeout(timer)
  }, [replayPlaying, replayIndex, replayEvents.length])

  const replayCapturedJourney = () => {
    // Snapshot the sequence once so streaming events cannot shift event 1.
    const sourceEvents = persistedLiveEvents.length ? persistedLiveEvents : liveActivityEvents
    if (!sourceEvents.length) {
      setLiveStatus('No captured events are available to replay.')
      return
    }
    const snapshot = [...sourceEvents]
    const replayPayload = replayInteractions.length ? replayInteractions : snapshot.map((event) => ({
      action: event.recorded_action || (String(event.type || '').includes('click') ? 'click' : 'inspect'),
      element: event.element || event.title || '',
      selector: event.selector || '',
      replay_selector: event.selector || '',
      value: event.value || '',
      page_url: event.url || '',
      destination_url: event.destination_url || '',
      coordinates: event.coordinates || {},
    }))
    setReplayEvents(snapshot)
    setReplayIndex(0)
    setReplayPlaying(snapshot.length > 1)
    setLiveStatus(`Replaying captured journey: event 1 of ${snapshot.length}.`)
    setLiveEvents([])
    const url = detail?.starting_url || detail?.source_url || detail?.application_url
    if (url) {
      api.replayLiveBrowser({ url, events: replayPayload }).catch((error) => {
        setReplayPlaying(false)
        setLiveStatus('Recorded replay unavailable: ' + (error.message || 'browser replay failed'))
      })
    }
  }

  useEffect(() => {
    if (activeTab !== 'live-browser' || !detail?.journey_id || !replayInteractions.length) return
    if (replayStartedRef.current === detail.journey_id) return
    replayStartedRef.current = detail.journey_id
    replayCapturedJourney()
  }, [activeTab, detail?.journey_id, replayInteractions.length])
  const rows = data.map((j) => (
    <tr
      key={j.journey_id}
      onClick={() => manageMode ? toggleJourneyForDelete(j.journey_id) : navigate(`/journeys/${encodeURIComponent(j.journey_id)}`)}
      className={selectedForDelete.includes(j.journey_id) ? 'row-marked-for-delete' : ''}
    >
      {manageMode ? <td>
        <input
          type="checkbox"
          aria-label={`Select ${j.journey_title || 'journey'} for deletion`}
          checked={selectedForDelete.includes(j.journey_id)}
          onClick={(event) => event.stopPropagation()}
          onChange={() => toggleJourneyForDelete(j.journey_id)}
        />
      </td> : null}
      <td>
        <strong>{j.journey_title || 'Journey'}</strong>
        <small className="journey-row-url">{j.starting_url || j.source_url || j.application_url || '-'}</small>
      </td>
      <td><Badge tone={String(j.outcome || '').toLowerCase().includes('complete') ? 'success' : 'warning'}>{j.outcome || 'Captured'}</Badge></td>
      <td><Badge tone="info">{j.step_count ?? j.steps?.length ?? 0} steps</Badge></td>
      <td><Badge tone="neutral">{j.interaction_count ?? j.events?.length ?? 0} events</Badge></td>
      <td>
        {manageMode ? (
          <button className="secondary-button table-danger-button" onClick={(event) => { event.stopPropagation(); handleRowDelete(j.journey_id) }} disabled={loading}>Delete</button>
        ) : (
          <button className="secondary-button" onClick={(event) => { event.stopPropagation(); navigate(`/journeys/${encodeURIComponent(j.journey_id)}`) }}>View Details</button>
        )}
      </td>
    </tr>
  ))

  const renderActiveTab = () => {
    if (!detail) {
      return null
    }

    if (activeTab === 'journey-detail') {
      const startingUrl = detail.starting_url || selectedJourney?.starting_url || selectedJourney?.application_url
      const applicationUrl = detail.application_url || selectedJourney?.application_url || metadata.app_url
      const sourceUrl = detail.source_url || selectedJourney?.source_url || selectedJourney?.application_url
      const viewport = metadata.viewport?.width ? `${metadata.viewport.width} x ${metadata.viewport.height}` : formatValue(metadata.viewport)
      const outcomeTone = String(detail.outcome || '').toLowerCase().includes('complete') ? 'success' : 'info'
      const captureSource = detail.test_hints?.capture_source || metadata.browser || 'unknown'
      const captureError = detail.test_hints?.playwright_error || detail.test_hints?.browser_use_error || ''

      return (
        <section className="journey-report journey-report-compact">
          <div className="journey-report-header">
            <div>
              <p className="journey-report-kicker">Journey Details</p>
              <h2>{detail.journey_title || selectedJourney?.journey_title || 'Selected Journey'}</h2>
              <p>{detail.summary || detail.reasoning || `${steps.length} steps captured from ${startingUrl || 'the selected application'}.`}</p>
            </div>
            <Badge tone={outcomeTone}>{detail.outcome || 'Discovered'}</Badge>
          </div>
          <div className={captureError ? 'journey-capture-alert danger' : 'journey-capture-alert'}>
            <strong>Capture source:</strong> {captureSource}
            {captureError ? <span> Browser automation did not run: {captureError}</span> : <span> Detailed browser evidence is available in Steps &amp; Interactions.</span>}
          </div>
          <div className="journey-report-meta">
            <div>
              <span>Steps</span>
              <strong>{steps.length}</strong>
            </div>
            <div>
              <span>Events</span>
              <strong>{detail.event_count ?? selectedJourney?.interaction_count ?? detail.events?.length ?? 0}</strong>
            </div>
            <div>
              <span>Browser</span>
              <strong>{formatValue(metadata.browser)}</strong>
            </div>
          </div>

          <div className="journey-markdown-grid">
            <div className="journey-report-section">
              <h3>Starting Context</h3>
              <p><strong>Starting point:</strong> {formatValue(detail.starting_point || metadata.starting_feature)}</p>
              <p><strong>Starting URL:</strong> {formatValue(startingUrl)}</p>
              <p><strong>Application URL:</strong> {formatValue(applicationUrl)}</p>
              <p><strong>Source URL:</strong> {formatValue(sourceUrl)}</p>
            </div>

            <div className="journey-report-section">
              <h3>Exploration Metadata</h3>
              <ul>
                <li><strong>Task input:</strong> {formatValue(metadata.task_input)}</li>
                <li><strong>Viewport:</strong> {viewport}</li>
                <li><strong>Captured:</strong> {formatValue(metadata.exploration_timestamp)}</li>
                <li><strong>Pre-login scoped:</strong> {formatValue(metadata.is_pre_login_scoped)}</li>
                <li><strong>Journeys discovered:</strong> {formatValue(metadata.total_journeys_discovered)}</li>
              </ul>
            </div>
          </div>
        </section>
      )
    }

    if (activeTab === 'visualization') {
      return (
        <section className="card journey-visualization-card">
          <div className="journey-visualization-header">
            <div>
              <p className="journey-report-kicker">Flowchart</p>
              <h2>Journey Visualization</h2>
              <p>Auto-generated from the selected journey map.</p>
            </div>
            <button className="secondary-button" onClick={() => api.downloadMermaid(selected)} disabled={!selected || vizJourneyId !== selected || !svg}>Download Flowchart</button>
          </div>
          {vizLoading && <div className="empty-state journey-viz-loading">Generating visual representation...</div>}
          {svg ? (
            <div key={vizJourneyId} className="mermaid-panel journey-mermaid-canvas" dangerouslySetInnerHTML={{ __html: svg }} />
          ) : (
            <div className="empty-state journey-viz-loading">Open this tab after selecting a journey to generate the flowchart.</div>
          )}
        </section>
      )
    }

    if (activeTab === 'live-browser') {
      const streamUrl = import.meta.env.VITE_BROWSER_STREAM_URL || ''
      const currentReplayEvent = replayIndex >= 0 ? replayEvents[replayIndex] : latestLiveEvent
      const currentUrl = currentReplayEvent?.destination_url || currentReplayEvent?.url || detail.starting_url || selectedJourney?.starting_url || '-'
      return (
        <section className="live-browser-panel live-browser-panel-refined">
          <div className="live-browser-workspace">
            <div className="live-browser-column">
              <div className="live-browser-window">
                <div className="live-browser-chrome">
                  <div className="browser-window-dots" aria-hidden="true"><span /><span /><span /></div>
                  <div className="live-browser-address">{currentUrl}</div>
                </div>
                <div className="live-browser-frame-wrap">
                  {streamUrl ? (
                    <div className="live-browser-stage">
                      <iframe
                        key={`${selected}-${streamUrl}`}
                        title="Live browser agent session"
                        src={streamUrl}
                        className="live-browser-frame"
                        tabIndex={-1}
                        aria-label="Read-only browser agent stream"
                        onError={() => setMessage('Live browser stream is unavailable. The journey evidence remains available below.')}
                      />
                      <div className="live-browser-readonly-overlay" aria-hidden="true">
                        <span>Agent controlled</span>
                        {liveActivityEvents.filter((event) => event.coordinates?.x !== undefined).slice(-8).map((event, index) => (
                          <span key={`${event.timestamp}-${index}`} className="live-click-marker" style={{ left: `${(event.coordinates.x / 1280) * 100}%`, top: `${(event.coordinates.y / 800) * 100}%` }} title={event.element || event.action || 'Agent interaction'} />
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="live-browser-unavailable">
                      <strong>Live browser stream is not configured</strong>
                      <span>Start the headed browser and noVNC stream, then set <code>VITE_BROWSER_STREAM_URL</code> to its browser URL.</span>
                    </div>
                  )}
                </div>
              </div>
              <div className="live-browser-controls">
                <Badge tone={replayPlaying ? 'success' : 'neutral'}>{replayPlaying ? 'Playing' : 'Ready'}</Badge>
                <button type="button" className="secondary-button" onClick={replayCapturedJourney} disabled={!liveActivityEvents.length}>↻ Restart replay</button>
                <button type="button" className="secondary-button" onClick={() => setReplayPlaying((playing) => !playing)} disabled={replayIndex < 0 || replayIndex >= replayEvents.length - 1}>{replayPlaying ? 'Ⅱ Pause' : '▷ Play'}</button>
                <button type="button" className="secondary-button live-step-button" onClick={() => setReplayIndex((index) => Math.max(0, index - 1))} disabled={replayIndex <= 0}>Previous</button>
                <button type="button" className="secondary-button live-step-button" onClick={() => setReplayIndex((index) => Math.min(replayEvents.length - 1, index + 1))} disabled={replayIndex < 0 || replayIndex >= replayEvents.length - 1}>Next</button>
              </div>
            </div>

            <aside className="live-activity-card">
              <div className="live-activity-current">
                <span className="live-activity-pulse" />
                <div>
                  <h2>{currentReplayEvent?.element || currentReplayEvent?.title || currentReplayEvent?.status || 'Waiting for browser activity'}</h2>
                  <p>{replayIndex >= 0 ? `Step ${replayIndex + 1} of ${replayEvents.length}` : `${liveActivityEvents.length} captured events`} · {currentReplayEvent?.result || liveStatus || 'Browser agent session ready'}</p>
                </div>
              </div>
              <div className="live-activity-divider" />
              <div className="live-activity-heading">
                <span>Activity Log</span>
                <Badge tone={liveActivityEvents.length ? 'success' : 'neutral'}>{liveActivityEvents.length}</Badge>
              </div>
              <div ref={liveTimelineRef} className="live-activity-list" aria-label="Live browser event timeline">
                {liveActivityEvents.length ? liveActivityEvents.map((event, index) => {
                  const isCurrent = replayIndex === index
                  return (
                    <div className={`live-activity-item ${isCurrent ? 'current' : ''}`} key={`${event.timestamp}-${index}`}>
                      <span className="live-activity-dot" />
                      <div>
                        <strong>{event.element || event.title || event.status || event.type}</strong>
                        <small>{event.result || event.destination_url || event.expected_destination || event.url || '-'}</small>
                      </div>
                      <time>{formatActivityTime(event.timestamp)}</time>
                    </div>
                  )
                }) : <div className="live-activity-empty">Start exploration to observe browser-agent activity.</div>}
              </div>
            </aside>
          </div>

          <div className="live-browser-observability-grid live-browser-observability-grid-rich live-browser-diagnostics">
            <div className="live-browser-current-state">
              <span className="journey-report-kicker">Agent state</span>
              <strong>{latestLiveEvent?.status || liveStatus || 'Waiting for activity'}</strong>
              <span>{latestLiveEvent?.title || detail.starting_url || '-'}</span>
              <code>{latestLiveEvent?.url || detail.starting_url || '-'}</code>
            </div>
            <div className="live-browser-current-state">
              <span className="journey-report-kicker">Selected target</span>
              <strong>{lastTargetEvent?.element || lastClickEvent?.element || 'No target selected yet'}</strong>
              <span>{lastTargetEvent?.selector || lastClickEvent?.selector || '-'}</span>
              <code>{lastTargetEvent?.expected_destination || lastClickEvent?.destination_url || lastClickEvent?.url || '-'}</code>
            </div>
            <div className="live-browser-current-state">
              <span className="journey-report-kicker">Page inventory</span>
              <strong>{lastScanEvent?.result || 'Waiting for DOM scan'}</strong>
              <span>{lastScanEvent?.visible_elements?.slice(0, 4).map((item) => `${item.type}: ${item.label}`).join(' | ') || 'Visible controls will appear here.'}</span>
              <code>{lastScanEvent?.counts ? JSON.stringify(lastScanEvent.counts) : '-'}</code>
            </div>
          </div>
        </section>
      )
    }
    if (activeTab === 'enrichment') {
      const combinedStatus = rawUiElements.length ? 'DOM and browser evidence available' : (steps.length ? 'Browser interaction evidence available' : 'Legacy evidence')

      return (
        <section className="journey-report journey-report-compact">
          <div className="journey-report-header">
            <div>
              <p className="journey-report-kicker">Step 1.5 Enrichment</p>
              <h2>Evidence & UI Elements</h2>
              <p>Shows the evidence package used by downstream story, test-case, and script generation. Separate DOM extraction is clearly marked when available; otherwise the UI evidence is derived from captured browser interactions.</p>
            </div>
            <Badge tone={detail.browser_agent_section || steps.length ? 'success' : 'warning'}>{combinedStatus}</Badge>
          </div>
          <div className="journey-report-meta">
            <div>
              <span>Journey Records</span>
              <strong>{browserJourneys.length}</strong>
            </div>
            <div>
              <span>DOM Pages</span>
              <strong>{rawUiElements.length}</strong>
            </div>
            <div>
              <span>Evidence Mode</span>
              <strong>{rawUiElements.length ? 'DOM enriched' : (steps.length ? 'Interaction derived' : 'Legacy')}</strong>
            </div>
          </div>



          <div className="journey-markdown-grid">
            <div className="journey-report-section">
              <h3>Evidence Sections</h3>
              <ul>
                <li><strong>Browser interaction evidence:</strong> {detail.browser_agent_section || steps.length ? 'Available' : 'Not available'}</li>
                <li><strong>Separate DOM/UI extraction:</strong> {rawUiElements.length ? 'Available' : 'Not captured separately; using interaction evidence'}</li>
                <li><strong>Selected journey:</strong> {formatValue(selectedJourney?.journey_title || 'Current journey')}</li>
              </ul>
            </div>

            <div className="journey-report-section">
              <h3>UI Evidence Coverage</h3>
              <ul>
                <li><strong>DOM extraction pages:</strong> {rawUiElements.length}</li>
                <li><strong>Evidence pages shown:</strong> {uiElements.length}</li>
                <li><strong>UI evidence items:</strong> {uiElements.reduce((total, page) => total + (page.extracted_url_ui_elements?.page?.total_elements ?? page.extracted_url_ui_elements?.page?.elements?.length ?? 0), 0)}</li>
                <li><strong>Login-context pages:</strong> {uiElements.filter((page) => page.is_login_flow_context).length}</li>
              </ul>
            </div>
          </div>

          <div className="journey-report-section journey-report-table-section">
            <h3>Page-Level UI Evidence</h3>
            {uiElements.length ? (
              <div className="page-evidence-cards">
                {uiElements.map((page) => {
                  const count = page.extracted_url_ui_elements?.page?.total_elements ?? page.extracted_url_ui_elements?.page?.elements?.length ?? 0
                  const isOpen = Boolean(openEvidencePages[page.page_url])
                  return (
                    <article className="page-evidence-card" key={page.page_url}>
                      <button type="button" className="page-evidence-card-toggle" onClick={() => setOpenEvidencePages((current) => ({ ...current, [page.page_url]: !current[page.page_url] }))} aria-expanded={isOpen}>
                        <span><strong>{page.page_url}</strong><small>{count} UI evidence items · {page.source_file || (rawUiElements.length ? 'DOM extraction' : 'Captured interactions')}</small></span>
                        <span aria-hidden="true">{isOpen ? '−' : '+'}</span>
                      </button>
                      {isOpen ? (
                        <div className="page-evidence-card-body">
                          <p><strong>Login context:</strong> {String(page.is_login_flow_context)}</p>
                          {page.extracted_url_ui_elements?.page?.elements?.length ? <pre>{JSON.stringify(page.extracted_url_ui_elements.page.elements, null, 2)}</pre> : <p>No detailed UI elements were captured for this page.</p>}
                        </div>
                      ) : null}
                    </article>
                  )
                })}
              </div>
            ) : (
              <p>No separate DOM/UI extraction file was captured for this journey. The table above may still show page-level evidence derived from browser interactions; full click and navigation details are in Steps &amp; Interactions.</p>
            )}
          </div>
        </section>
      )
    }

    if (activeTab === 'flow-details') {
      if (evidenceLoading && evidenceJourneyId !== selected) {
        return <div className="empty-state">Loading complete page evidence...</div>
      }
      const capturedTitleCount = pageEvidence.reduce((total, page) => total + page.headings.length, 0)
      const capturedCardCount = pageEvidence.reduce((total, page) => total + page.cards.length, 0)
      const evidencedPageCount = pageEvidence.filter((page) => page.domSnapshotCount || page.screenshots.length).length

      return (
        <section className="journey-report journey-report-compact page-evidence-report">
          <div className="journey-report-header">
            <div>
              <p className="journey-report-kicker">Exploration Report</p>
              <h2>Page Evidence</h2>
              <p>Each explored URL is shown once with the useful content captured from that page. Technical automation data is available only when you need it.</p>
            </div>
            <Badge tone={pageEvidence.length ? 'success' : 'neutral'}>{pageEvidence.length} pages</Badge>
          </div>
          <div className="journey-report-meta page-evidence-summary">
            <div>
              <span>Explored Pages</span>
              <strong>{pageEvidence.length}</strong>
            </div>
            <div>
              <span>Titles &amp; Headings</span>
              <strong>{capturedTitleCount}</strong>
            </div>
            <div>
              <span>Cards Captured</span>
              <strong>{capturedCardCount}</strong>
            </div>
            <div>
              <span>Pages With Evidence</span>
              <strong>{evidencedPageCount}</strong>
            </div>
          </div>

          {pageEvidence.length ? (
            <div className="page-evidence-list">
              {pageEvidence.map((page, pageIndex) => (
                <article key={page.url} className="page-evidence-card">
                  {(() => {
                      const isOpen = Boolean(openEvidencePages[`page:${page.url}`])
                    return <>
                  <header className="page-evidence-card-head">
                    <div className="page-evidence-index">{pageIndex + 1}</div>
                    <div>
                      <span className="journey-report-kicker">Explored page</span>
                      <h3>{page.title}</h3>
                      <a href={page.url.startsWith('http') ? page.url : undefined} target="_blank" rel="noreferrer">{page.url}</a>
                    </div>
                    <div className="page-evidence-badges">
                      <Badge tone="neutral">{page.headings.length} titles</Badge>
                      <Badge tone={page.cards.length ? 'success' : 'neutral'}>{page.cards.length} cards</Badge>
                      <button type="button" className="secondary-button" onClick={() => setOpenEvidencePages((current) => ({ ...current, [`page:${page.url}`]: !isOpen }))}>{isOpen ? 'Collapse' : 'Open'}</button>
                    </div>
                  </header>

                  {isOpen ? <>

                  <div className="page-evidence-content-grid">
                    <section className="page-evidence-content-section">
                      <h4>Titles &amp; Headings</h4>
                      {page.headings.length ? (
                        <ul className="page-evidence-title-list">
                          {page.headings.map((heading, index) => <li key={`${page.url}-heading-${index}`}>{heading}</li>)}
                        </ul>
                      ) : <p className="page-evidence-empty">No page headings were captured.</p>}
                    </section>

                    <section className="page-evidence-content-section page-evidence-card-content">
                      <h4>Cards &amp; Content</h4>
                      {page.cards.length ? (
                        <div className="page-evidence-captured-cards">
                          {page.cards.map((card, index) => (
                            <div className="page-evidence-captured-card" key={`${page.url}-card-${index}`}>
                              <strong>{card.title}</strong>
                              {card.description ? <p>{card.description}</p> : null}
                              {card.imageAlt ? <small>Image: {card.imageAlt}</small> : null}
                              {card.cta ? <span>{card.cta}</span> : null}
                              {card.destinationUrl ? <small>Destination: {card.destinationUrl}</small> : null}
                            </div>
                          ))}
                        </div>
                      ) : <p className="page-evidence-empty">No structured cards were identified on this page.</p>}
                    </section>
                  </div>

                  {page.descriptions.length ? (
                    <section className="page-evidence-content-section page-evidence-descriptions">
                      <h4>Descriptions</h4>
                      <ul>
                        {page.descriptions.map((description, index) => <li key={`${page.url}-description-${index}`}>{description}</li>)}
                      </ul>
                    </section>
                  ) : null}

                  {page.ctas.length ? (
                    <section className="page-evidence-content-section page-evidence-ctas">
                      <h4>Important Links &amp; CTAs</h4>
                      <div>{page.ctas.map((cta, index) => <span key={`${page.url}-cta-${index}`}>{cta}</span>)}</div>
                    </section>
                  ) : null}

                  <details className="page-evidence-disclosure">
                    <summary>View page evidence</summary>
                    <div className="page-evidence-proof-grid">
                      <div><span>Journey steps</span><strong>{page.stepNumbers.join(', ')}</strong></div>
                      <div><span>Captured interactions</span><strong>{page.interactions.length}</strong></div>
                      <div><span>DOM snapshots</span><strong>{page.domSnapshotCount}</strong></div>
                      <div><span>Screenshots</span><strong>{page.screenshots.length}</strong></div>
                    </div>
                    {page.screenshots.length ? (
                      <div className="page-evidence-files">
                        <strong>Screenshot evidence</strong>
                        {page.screenshots.map((path, index) => <code key={`${page.url}-screenshot-${index}`}>{path}</code>)}
                      </div>
                    ) : <p className="page-evidence-empty">No screenshot path was attached to this page.</p>}
                  </details>

                  {page.interactions.length ? (
                    <details className="page-evidence-disclosure page-evidence-advanced">
                      <summary>Advanced technical evidence ({page.interactions.length})</summary>
                      <Table
                        columns={['Action', 'Element', 'Result', 'Technical Evidence']}
                        rows={page.interactions.map((interaction, index) => (
                          <tr key={`${page.url}-interaction-${interaction.sequence_id ?? index}`}>
                            <td>{interaction.action || 'inspect'}</td>
                            <td>{interaction.element_label || interaction.element_type || '-'}</td>
                            <td>{interaction.resulted_in || '-'}</td>
                            <td>
                              <details className="interaction-evidence">
                                <summary>Technical details</summary>
                                <div className="interaction-evidence-grid">
                                  <span>Selector</span><strong>{formatValue(interaction.selector)}</strong>
                                  <span>Destination</span><strong>{formatValue(interaction.destination_url)}</strong>
                                  <span>Role</span><strong>{formatValue(interaction.role)}</strong>
                                  <span>Timestamp</span><strong>{formatValue(interaction.event_timestamp)}</strong>
                                  <span>Coordinates</span><strong>{formatValue(interaction.coordinates)}</strong>
                                  <span>Network events</span><strong>{interaction.network_events?.length ?? 0}</strong>
                                  <span>Replay selector</span><strong>{formatValue(interaction.replay?.selector)}</strong>
                                </div>
                              </details>
                            </td>
                          </tr>
                        ))}
                      />
                    </details>
                  ) : null}
                  </> : null}
                    </>
                  })()}
                </article>
              ))}
            </div>
          ) : (
            <div className="page-evidence-empty-state">
              <strong>No page evidence was captured for this journey.</strong>
              <span>Run exploration again to collect page titles, cards, descriptions, and screenshots.</span>
            </div>
          )}
        </section>
      )
    }
    return null
  }

  const pageTitle = showJourneyList ? '' : (detail?.journey_title || 'Journey Review')
  const pageSubtitle = showJourneyList
    ? ''
    : 'Review the objective, browser exploration, visualization, replay, and page evidence for this journey.'

  return (
    <Card
      className={showJourneyList ? 'journey-list-flat' : 'journey-review-flat'}
      title={pageTitle}
      subtitle={pageSubtitle}
      actions={showJourneyList ? (
        <>
          {data.length ? <button onClick={() => onCreateJourney ? onCreateJourney() : navigate('/workflow?create=1')}>Create New Journey</button> : null}
          <button className="secondary-button" onClick={() => { setManageMode((current) => !current); setSelectedForDelete([]) }} disabled={loading || !data.length}>{manageMode ? 'Done Managing' : 'Manage Journeys'}</button>
          <button className="secondary-button utility-action" onClick={load} disabled={loading}>
            <span className={loading ? 'utility-action-icon spinning' : 'utility-action-icon'} aria-hidden="true">&#8635;</span>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </>
      ) : null}
    >
      {showJourneyList && manageMode ? <div className="journey-selection-toolbar">
        <label className="journey-select-all">
          <input
            type="checkbox"
            ref={(input) => { if (input) input.indeterminate = selectedForDelete.length > 0 && selectedForDelete.length < data.length }}
            checked={Boolean(data.length) && selectedForDelete.length === data.length}
            onChange={toggleAllJourneysForDelete}
            disabled={loading || !data.length}
          />
          <span>{selectedForDelete.length ? `${selectedForDelete.length} selected` : 'Select journeys to delete'}</span>
        </label>
        <button
          type="button"
          className="secondary-button delete-selected-button"
          onClick={deleteSelectedJourneys}
          disabled={loading || !selectedForDelete.length}
        >
          Delete selected
        </button>
        <button type="button" className="secondary-button" onClick={deleteJourneys} disabled={loading || !data.length}>Delete All Journeys</button>
      </div> : null}
      {showJourneyList && data.length ? <Table columns={manageMode ? ['Select for deletion', 'Journey', 'Status', 'Steps', 'Events', 'Action'] : ['Journey', 'Status', 'Steps', 'Events', 'Action']} rows={rows} /> : null}
      {showJourneyList && !loading && !data.length ? (
        <div className="journey-onboarding-empty">
          <span className="eyebrow">Get started</span>
          <h3>No journeys created yet</h3>
          <p>Describe what you want the browser agent to explore and create your first journey.</p>
          <button type="button" onClick={() => onCreateJourney ? onCreateJourney() : navigate('/workflow?create=1')}>Create Your First Journey</button>
        </div>
      ) : null}
      <div className="inline-actions">
        {message && <div className="notification-row"><Badge tone={message.includes('deleted') ? 'danger' : 'warning'}>{message}</Badge></div>}
      </div>

      {!showJourneyList && detail && (
        <div ref={detailRef} className="detail-tabs-shell">
          <div className="detail-tabs-navigation">
            <span className="detail-tabs-label">Views</span>
            <div className="detail-tabs">
              {detailTabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={`detail-tab ${activeTab === tab.id ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
          <div className="detail-tab-panel">
            {renderActiveTab()}
          </div>
          {!showJourneyList ? <div className="journey-detail-primary-action journey-detail-primary-action-bottom">
            <div className="journey-fixed-stage">
              <strong>Stage 1 of 5</strong>
              <span aria-hidden="true">•</span>
              <span>{detail.journey_title || selectedJourney?.journey_title || 'Journey review'}</span>
            </div>
            <div className="journey-fixed-footer-actions">
              <button type="button" className="secondary-button" onClick={() => navigate('/workflow')}>Back to Journeys</button>
              <button type="button" onClick={() => navigate(`/stories?journey=${encodeURIComponent(selected)}`)}>Continue to User Stories <span aria-hidden="true">→</span></button>
            </div>
          </div> : null}
        </div>
      )}
    </Card>
  )
}
