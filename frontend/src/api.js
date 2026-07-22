// Same-origin by default: the frontend proxy forwards /api to the backend.
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

async function download(path, filename) {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(await res.text())
  const blob = await res.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

export const api = {
  startExploration: (payload) => request('/exploration/start', { method: 'POST', body: JSON.stringify(payload) }),
  getJourneys: () => request('/journeys'), resetJourneys: () => request('/journeys', { method: 'DELETE' }),
  deleteJourney: (journeyId) => request(`/journeys/${journeyId}`, { method: 'DELETE' }), getJourney: (journeyId) => request(`/journeys/${journeyId}`),
  visualizeJourney: (payload) => request('/journeys/visualize', { method: 'POST', body: JSON.stringify(payload) }), downloadMermaid: (journeyId) => download(`/journeys/${journeyId}/mermaid/download`, `journey_${journeyId}_mermaid.mmd`),
  getConfiguration: () => request('/configuration'), getLLMModels: () => request('/configuration/llm-models'), saveConfiguration: (payload) => request('/configuration', { method: 'POST', body: JSON.stringify(payload) }), testJira: (payload) => request('/configuration/test-jira', { method: 'POST', body: JSON.stringify(payload) }), testLLM: (payload) => request('/configuration/test-llm', { method: 'POST', body: JSON.stringify(payload) }),
  generateUserStories: (payload) => request('/user-stories/generate', { method: 'POST', body: JSON.stringify(payload) }), syncUserStoriesToJira: (payload) => request('/user-stories/sync-jira', { method: 'POST', body: JSON.stringify(payload) }), getUserStories: () => request('/user-stories'), downloadUserStories: () => download('/user-stories/download', 'user_stories.json'),
  generateTestCases: (payload) => request('/test-cases/generate', { method: 'POST', body: JSON.stringify(payload) }), getTestCases: () => request('/test-cases'), downloadTestCases: () => download('/test-cases/download', 'test_cases.json'), generateTestScripts: (payload) => request('/test-scripts/generate', { method: 'POST', body: JSON.stringify(payload) }), getTestScripts: () => request('/test-scripts'), downloadTestScripts: () => download('/test-scripts/download', 'test_scripts.json'),
  exportArtifact: (artifactType) => request(`/export/${artifactType}`), downloadArtifact: (artifactType) => download(`/export/${artifactType}/download`, `${artifactType}.json`), runPipeline: (payload) => request('/pipeline/run-all', { method: 'POST', body: JSON.stringify(payload ?? {}) }), runReporting: (payload) => request('/reporting/run', { method: 'POST', body: JSON.stringify(payload) }), runSummary: (payload) => request('/summary/run', { method: 'POST', body: JSON.stringify(payload ?? {}) }),
}