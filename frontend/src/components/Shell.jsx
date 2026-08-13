import React from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

export const navItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/workflow', label: 'Workflow' },
  { path: '/configuration', label: 'Configuration Settings' },
]

const pipelineSteps = [
  { path: '/workflow', label: 'Explore & Discover Journey' },
  { path: '/stories', label: 'Generate User Stories' },
  { path: '/tests', label: 'Generate Test Cases' },
  { path: '/scripts', label: 'Generate Test Scripts' },
  { path: '/export', label: 'Review and Export' },
]

const topbarLabels = {
  '/': 'Dashboard',
  '/workflow': 'Explore & Discover Journey',
  '/journeys': 'Explore & Discover Journey',
  '/stories': 'User Stories',
  '/tests': 'Test Cases',
  '/scripts': 'Test Scripts',
  '/export': 'Review & Export',
  '/reporting': 'Reporting',
  '/summary': 'Summary',
}

function getStepState(pathname, index) {
  const currentIndex = pipelineSteps.findIndex((step) => step.path === pathname || ((pathname === '/visualization' || pathname === '/journeys') && step.path === '/workflow'))
  if (currentIndex === -1) return index < 1 ? 'completed' : index === 0 ? 'current' : 'locked'
  if (index < currentIndex) return 'completed'
  if (index === currentIndex) return 'current'
  return 'locked'
}

function getCurrentIndex(pathname) {
  return pipelineSteps.findIndex((step) => step.path === pathname || ((pathname === '/visualization' || pathname === '/journeys') && step.path === '/workflow'))
}

const workflowPaths = new Set(['/workflow', '/journeys', '/stories', '/tests', '/scripts', '/export', '/visualization'])

export function Shell() {
  const location = useLocation()
  const navigate = useNavigate()
  const currentIndex = getCurrentIndex(location.pathname)
  const previousStep = currentIndex > 0 ? pipelineSteps[currentIndex - 1] : null
  const nextStep = currentIndex >= 0 && currentIndex < pipelineSteps.length - 1 ? pipelineSteps[currentIndex + 1] : null
  const showWorkflowNav = workflowPaths.has(location.pathname)

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">
            <img src="/factspan_logo.svg" alt="Factspan" className="brand-logo" />
          </div>
          <div className="brand-copy">
            <div className="brand">Journey AI</div>
            <div className="brand-subtitle">Enterprise journey discovery and test automation</div>
          </div>
        </div>
        <div className="sidebar-copy">AI-driven journey discovery, story generation, and automation planning.</div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) => `navlink ${isActive ? 'active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="main-frame">
        <header className="topbar">
          <div>
            <div className="topbar-title">Journey AI Control Center</div>
            <div className="topbar-subtitle">{topbarLabels[location.pathname] || location.pathname.replace('/', '').replace('-', ' ')}</div>
          </div>
        </header>
        <main className="content">
          {showWorkflowNav && (
            <div className="pipeline-stepper">
              {pipelineSteps.map((step, index) => {
                const state = getStepState(location.pathname, index)
                return (
                  <button
                    key={step.path}
                    type="button"
                    className={`pipeline-stepper-item ${state}`}
                    onClick={() => {
                      if (state !== 'locked') navigate(step.path)
                    }}
                    disabled={state === 'locked'}
                  >
                    <span className="pipeline-stepper-index">{index + 1}</span>
                    <div>
                      <strong>{step.label}</strong>
                      <small>{state === 'current' ? 'Current step' : state === 'completed' ? 'Completed' : 'Locked'}</small>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
          <Outlet />
          {showWorkflowNav && (
            <div className="workflow-nav workflow-nav-bottom">
              <div className="workflow-nav-copy">
                <strong>{currentIndex >= 0 ? pipelineSteps[currentIndex]?.label : 'Pipeline'}</strong>
                <span>{currentIndex >= 0 ? `Step ${currentIndex + 1} of ${pipelineSteps.length}` : 'Step navigation'}</span>
              </div>
              <div className="workflow-nav-actions">
                <button type="button" className="secondary-button workflow-nav-button" onClick={() => previousStep && navigate(previousStep.path)} disabled={!previousStep}>
                  Previous
                </button>
                <button type="button" className="workflow-nav-button" onClick={() => nextStep && navigate(nextStep.path)} disabled={!nextStep}>
                  Next
                </button>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}