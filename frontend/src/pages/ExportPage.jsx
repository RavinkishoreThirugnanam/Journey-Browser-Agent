import React, { useState } from 'react'
import { api } from '../api'
import { ActionBar, Badge, Card } from '../components/Ui'

const filenames = {
  journeys: 'journeys.json',
  'user-stories': 'user_stories.json',
  'test-cases': 'test_cases.json',
  'test-scripts': 'test_scripts.json',
}

export function ExportPage() {
  const [artifactType, setArtifactType] = useState('journeys')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const exportArtifact = async () => {
    setLoading(true)
    try {
      setData(await api.exportArtifact(artifactType))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Review & Export" subtitle="Download journey maps, stories, test cases, and scripts from one place.">
      <div className="workflow-status-bar panel" style={{ marginTop: 18 }}>
        <div>
          <h3>Export Overview</h3>
          <p>Select an artifact, preview its payload, and download the generated file.</p>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 20 }}>
        <h3>Export Target</h3>
        <div className="stack" style={{ gap: 16 }}>
          <div className="field">
            <span>Artifact Type</span>
            <select className="journey-select" value={artifactType} onChange={(e) => setArtifactType(e.target.value)}>
              <option value="journeys">Journeys</option>
              <option value="user-stories">User Stories</option>
              <option value="test-cases">Test Cases</option>
              <option value="test-scripts">Test Scripts</option>
            </select>
          </div>
          <ActionBar>
            <button onClick={exportArtifact} disabled={loading}>{loading ? 'Preparing...' : 'Review Export Payload'}</button>
            <button className="secondary-button" onClick={() => api.downloadArtifact(artifactType)}>Download `{filenames[artifactType]}`</button>
          </ActionBar>
        </div>
      </div>
      {data && (
        <div className="panel payload-preview" style={{ marginTop: 20 }}>
          <h3>Payload Preview</h3>
          <pre className="code-block">{JSON.stringify(data, null, 2)}</pre>
        </div>
      )}
    </Card>
  )
}
