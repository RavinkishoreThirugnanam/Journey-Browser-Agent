const API_BASE = import.meta.env.VITE_API_BASE_URL

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
  getDashboardSummary: () => request('/dashboard/summary', { cache: 'no-store' }),
  startExploration: (payload) => request('/exploration/start', { method: 'POST', body: JSON.stringify(payload) }),
  getJourneys: () => request('/journeys?compact=true', { cache: 'no-store' }),
  resetJourneys: () => request('/journeys', { method: 'DELETE' }),
  deleteJourney: (journeyId) => request(`/journeys/${journeyId}`, { method: 'DELETE' }),
  deleteJourneys: (journeyIds) => request('/journeys/delete-selected', { method: 'POST', body: JSON.stringify({ journey_ids: journeyIds }) }),
  getJourney: (journeyId, includeEvidence = false) => request(`/journeys/${journeyId}?include_evidence=${includeEvidence}`),
  visualizeJourney: (payload) => request('/journeys/visualize', { method: 'POST', body: JSON.stringify(payload) }),
  downloadMermaid: (journeyId) => download(`/journeys/${journeyId}/mermaid/download`, `journey_${journeyId}_mermaid.mmd`),
  navigateLiveBrowser: (payload) => request('/browser/live/navigate', { method: 'POST', body: JSON.stringify(payload) }),
  replayLiveBrowser: (payload) => request('/browser/live/replay', { method: 'POST', body: JSON.stringify(payload) }),
  liveEventsUrl: (url) => `${API_BASE}/browser/live/events?url=${encodeURIComponent(url)}`,
  getConfiguration: () => request('/configuration'),
  getLLMModels: () => request('/configuration/llm-models'),
  saveConfiguration: (payload) => request('/configuration', { method: 'POST', body: JSON.stringify(payload) }),
  testJira: (payload) => request('/configuration/test-jira', { method: 'POST', body: JSON.stringify(payload) }),
  testLLM: (payload) => request('/configuration/test-llm', { method: 'POST', body: JSON.stringify(payload) }),
  generateUserStories: (payload) => request('/user-stories/generate', { method: 'POST', body: JSON.stringify(payload) }),
  syncUserStoriesToJira: (payload) => request('/user-stories/sync-jira', { method: 'POST', body: JSON.stringify(payload) }),
  refreshUserStoriesFromJira: (payload) => request('/user-stories/refresh-jira', { method: 'POST', body: JSON.stringify(payload) }),
  getUserStories: () => request('/user-stories'),
  deleteUserStory: (storyId) => request(`/user-stories/${storyId}`, { method: 'DELETE' }),
  resetUserStories: () => request('/user-stories', { method: 'DELETE' }),
  downloadUserStories: () => download('/user-stories/download', 'user_stories.json'),
  generateTestCases: (payload) => request('/test-cases/generate', { method: 'POST', body: JSON.stringify(payload) }),
  getTestCases: () => request('/test-cases'),
  downloadTestCases: () => download('/test-cases/download', 'test_cases.json'),
  generateTestScripts: (payload) => request('/test-scripts/generate', { method: 'POST', body: JSON.stringify(payload) }),
  getTestScripts: () => request('/test-scripts'),
  downloadTestScriptArtifact: (scriptId, format, filename) => download(`/test-scripts/${scriptId}/download/${format}`, filename),
  downloadTestScripts: () => download('/test-scripts/download', 'test_scripts.json'),
  exportArtifact: (artifactType, options = {}) => request(`/export/${artifactType}?preview=true`, options),
  downloadArtifact: (artifactType) => download(`/export/${artifactType}/download`, `${artifactType}.json`),
  runPipeline: (payload) => request('/pipeline/run-all', { method: 'POST', body: JSON.stringify(payload ?? {}) }),
  runReporting: (payload) => request('/reporting/run', { method: 'POST', body: JSON.stringify(payload) }),
  runSummary: (payload) => request('/summary/run', { method: 'POST', body: JSON.stringify(payload ?? {}) }),
}

