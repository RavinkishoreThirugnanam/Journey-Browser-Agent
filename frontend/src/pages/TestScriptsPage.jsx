import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { ActionBar, Badge, Card, Table } from '../components/Ui'
import { useFetch } from '../hooks/useFetch'

function EmptyState({ title, description }) {
  return (
    <div className="empty-card">
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  )
}

export function TestScriptsPage() {
  const { data, loading, refetch } = useFetch(api.getTestScripts, [])
  const items = data?.items ?? []
  const [testCases, setTestCases] = useState([])
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.getTestCases().then((d) => setTestCases(d.items ?? d ?? [])).catch(() => {})
  }, [])

  const generate = async () => {
    setMessage('')
    try {
      await api.generateTestScripts({ test_case_ids: testCases.map((t) => t.test_case_id) })
      setMessage('Test scripts generated successfully.')
      refetch()
    } catch {
      setMessage('Unable to generate test scripts.')
    }
  }

  return (
    <Card
      title="Test Scripts"
      subtitle="Generate feature files and JavaScript automation scaffolds."
      actions={<button onClick={refetch} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>}
    >
      <div className="workflow-status-bar panel" style={{ marginTop: 18 }}>
        <div>
          <h3>Script Generation Status</h3>
          <p>Generate scripts from the available test cases and keep the output aligned with the selected flow.</p>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 20 }}>
        <h3>Actions</h3>
        <ActionBar>
          <button onClick={generate} disabled={!testCases.length}>Generate Test Scripts</button>
        </ActionBar>
        {message && <div className="notification-row" style={{ marginTop: 12 }}><Badge tone={message.includes('success') ? 'success' : 'warning'}>{message}</Badge></div>}
      </div>

      {items.length ? (
        <Table
          columns={['Script ID', 'Test Case', 'Status']}
          rows={items.map((item) => (
            <tr key={item.script_id}>
              <td>{item.script_id}</td>
              <td>{item.test_case_id}</td>
              <td>{item.jira_url ? <a href={item.jira_url} target="_blank" rel="noreferrer">{item.jira_key || 'Open Jira'}</a> : <Badge tone={item.sync_status === 'local' ? 'warning' : 'neutral'}>{item.sync_status || 'local'}</Badge>}</td>
            </tr>
          ))}
        />
      ) : (
        <EmptyState title="No test scripts yet" description="Generate scripts from the test cases above." />
      )}
    </Card>
  )
}
