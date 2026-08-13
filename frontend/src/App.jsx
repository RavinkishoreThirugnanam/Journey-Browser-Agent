import React, { Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { DashboardPage } from './pages/DashboardPage'
import { WorkflowPage } from './pages/WorkflowPage'
import { JourneyPage } from './pages/JourneyPage'
import { ConfigurationPage } from './pages/ConfigurationPage'
import { UserStoriesPage } from './pages/UserStoriesPage'
import { TestCasesPage } from './pages/TestCasesPage'
import { TestScriptsPage } from './pages/TestScriptsPage'
import { ExportPage } from './pages/ExportPage'
import { ReportingPage } from './pages/ReportingPage'
import { SummaryPage } from './pages/SummaryPage'

export default function App() {
  return (
    <Suspense fallback={<div className="page-loading">Loading page...</div>}>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<DashboardPage />} />
          <Route path="workflow" element={<WorkflowPage />} />
          <Route path="journeys" element={<JourneyPage />} />
          <Route path="visualization" element={<Navigate to="/workflow" replace />} />
          <Route path="configuration" element={<ConfigurationPage />} />
          <Route path="stories" element={<UserStoriesPage />} />
          <Route path="tests" element={<TestCasesPage />} />
          <Route path="scripts" element={<TestScriptsPage />} />
          <Route path="export" element={<ExportPage />} />
          <Route path="reporting" element={<ReportingPage />} />
          <Route path="summary" element={<SummaryPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
