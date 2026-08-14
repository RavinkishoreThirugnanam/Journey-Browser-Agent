import React from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

const pipelineSteps = [
  { path: '/workflow', label: 'Create Journeys' },
  { path: '/stories', label: 'Generate User Stories' },
  { path: '/tests', label: 'Generate Test Cases' },
  { path: '/scripts', label: 'Generate Test Scripts' },
  { path: '/export', label: 'Review and Export' },
]

const topbarLabels = {
  '/': 'Dashboard',
  '/workflow': 'Create Journeys',
  '/journeys': 'Create Journeys',
  '/stories': 'User Stories',
  '/tests': 'Test Cases',
  '/scripts': 'Test Scripts',
  '/export': 'Review & Export',
  '/reporting': 'Reporting',
  '/summary': 'Summary',
}

function getTopbarLabel(pathname) {
  if (pathname.startsWith('/journeys/')) return 'Journey Review'
  return topbarLabels[pathname] || pathname.replace('/', '').replace('-', ' ')
}

function isJourneyCreationPath(pathname) {
  return pathname === '/workflow' || pathname === '/visualization' || pathname.startsWith('/journeys')
}

function SidebarIcon({ name }) {
  if (name === 'dashboard') {
    return (
      <svg className="sidebar-item-icon" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </svg>
    )
  }
  if (name === 'journey') {
    return (
      <svg className="sidebar-item-icon" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="5" cy="6" r="2" />
        <circle cx="19" cy="18" r="2" />
        <path d="M7 6h5a3 3 0 0 1 3 3v0a3 3 0 0 1-3 3H9a3 3 0 0 0-3 3v1" />
        <path d="m16 15 3 3 3-3" />
      </svg>
    )
  }
  return (
    <svg className="sidebar-item-icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.86 2.86-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21H9.5v-.1A1.7 1.7 0 0 0 8.4 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.86-2.86.06-.06A1.7 1.7 0 0 0 4 15a1.7 1.7 0 0 0-1.6-1H2v-4h.4A1.7 1.7 0 0 0 4 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06L6.46 4.2l.06.06A1.7 1.7 0 0 0 8.4 4 1.7 1.7 0 0 0 9.5 2.4V2h4v.4A1.7 1.7 0 0 0 15 4a1.7 1.7 0 0 0 1.88.26l.06-.06 2.86 2.86-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.6 1h1v4h-1a1.7 1.7 0 0 0-1.6 1Z" />
    </svg>
  )
}

export function Shell() {
  const location = useLocation()
  const currentParams = new URLSearchParams(location.search)
  const detailJourneyId = location.pathname.startsWith('/journeys/')
    ? decodeURIComponent(location.pathname.split('/')[2] || '')
    : ''
  const journeyContext = currentParams.get('journeys')
    ? `journeys=${encodeURIComponent(currentParams.get('journeys'))}`
    : ((currentParams.get('journey') || detailJourneyId)
      ? `journey=${encodeURIComponent(currentParams.get('journey') || detailJourneyId)}`
      : '')
  const pipelineTarget = (path) => path === '/workflow' || !journeyContext ? path : `${path}?${journeyContext}`

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">
            <img src="/factspan_logo.svg" alt="Factspan" className="brand-logo" />
          </div>
          <div className="brand-copy">
            <div className="brand">FLUX JOURNEY AI</div>
            <div className="brand-subtitle">AI-powered QA and test automation</div>
          </div>
        </div>
        <div className="sidebar-copy">Discover application journeys and turn them into test-ready requirements, cases, and automation.</div>
        <nav className="nav">
          <NavLink to="/" end className={({ isActive }) => `navlink sidebar-primary-link ${isActive ? 'active' : ''}`}>
            <SidebarIcon name="dashboard" />
            <span>Overview</span>
          </NavLink>

          <div className="sidebar-nav-group">
            <div className="sidebar-nav-group-title">
              <div className="sidebar-group-label">
                <SidebarIcon name="journey" />
                <span>Create Journeys</span>
              </div>
              <small>5 steps</small>
            </div>
            <div className="sidebar-submenu">
              {pipelineSteps.map((step, index) => (
                <NavLink
                  key={step.path}
                  to={pipelineTarget(step.path)}
                  className={({ isActive }) => {
                    const active = step.path === '/workflow' ? isJourneyCreationPath(location.pathname) : isActive
                    return `sidebar-submenu-link ${active ? 'active' : ''}`
                  }}
                >
                  <span className="sidebar-submenu-index">{index + 1}</span>
                  <span>{step.label}</span>
                </NavLink>
              ))}
            </div>
          </div>

          <NavLink to="/configuration" className={({ isActive }) => `navlink sidebar-primary-link ${isActive ? 'active' : ''}`}>
            <SidebarIcon name="settings" />
            <span>Configuration Settings</span>
          </NavLink>
        </nav>
      </aside>
      <div className="main-frame">
        <header className="topbar">
          <div>
            <div className="topbar-title">QA Automation Control Center</div>
            <div className="topbar-subtitle">{getTopbarLabel(location.pathname)}</div>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
