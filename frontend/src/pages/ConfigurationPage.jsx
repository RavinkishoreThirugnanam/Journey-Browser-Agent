import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Badge, Card, Field } from '../components/Ui'

const DEFAULT_MODELS = [
  { provider: 'OpenAI', model: 'gpt-4o-mini', label: 'GPT-4o mini' },
  { provider: 'OpenAI', model: 'gpt-4.1-mini', label: 'GPT-4.1 mini' },
  { provider: 'OpenAI', model: 'gpt-4.1', label: 'GPT-4.1' },
  { provider: 'OpenAI', model: 'gpt-5', label: 'GPT-5' },
]

const TEST_CASE_ISSUE_TYPES = ['Test', 'Task', 'Story', 'Bug']

export function ConfigurationPage() {
  const [modelCatalog, setModelCatalog] = useState(DEFAULT_MODELS)
  const [form, setForm] = useState({ jira: { base_url: '', project_key: '', username: '', api_token: '', auth_type: 'basic', issue_type: 'Story', test_case_issue_type: 'Test' }, llm: { provider: 'OpenAI', model: 'gpt-4o-mini', supervisor_model: 'gpt-4o-mini', api_endpoint: '', auth_token: '', temperature: 0.2, browser_timeout_screenshot: 30.0, browser_timeout_navigate: 30.0, browser_use_enabled: false }, application: { base_url: '', environment: 'development', default_project: '', global_parameters: {}, browser_headers: {} } })
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.getLLMModels().then((payload) => {
      if (Array.isArray(payload.models) && payload.models.length) setModelCatalog(payload.models)
    }).catch(() => {})
  }, [])

  const load = async () => {
    try {
      const config = await api.getConfiguration()
      setForm((current) => ({ jira: { ...current.jira, ...(config.jira ?? {}) }, llm: config.llm ?? current.llm, application: config.application ?? current.application }))
    } catch {}
  }

  useEffect(() => { load() }, [])

  const save = async (e) => {
    e.preventDefault()
    try {
      await api.saveConfiguration(form)
      setMessage('Configuration saved successfully.')
    } catch {
      setMessage('Failed to save configuration.')
    }
  }

  const testJira = async () => {
    try {
      const result = await api.testJira(form)
      setMessage(result.message)
    } catch {
      setMessage('Jira validation failed.')
    }
  }

  const testLLM = async () => {
    try {
      const result = await api.testLLM(form)
      setMessage(result.message)
    } catch {
      setMessage('LLM validation failed.')
    }
  }

  const modelOptions = useMemo(() => modelCatalog, [modelCatalog])

  return (
    <Card title="Configuration Settings" subtitle="Persist Jira, LLM, and application settings in one place.">
      <form onSubmit={save} className="stack">
        <div className="grid two">
          <section className="panel">
            <h3>Application Settings</h3>
            <Field label="Base URL"><input value={form.application.base_url} onChange={(e) => setForm({ ...form, application: { ...form.application, base_url: e.target.value } })} /></Field>
            <Field label="Environment"><input value={form.application.environment} onChange={(e) => setForm({ ...form, application: { ...form.application, environment: e.target.value } })} /></Field>
            <Field label="Default Project"><input value={form.application.default_project} onChange={(e) => setForm({ ...form, application: { ...form.application, default_project: e.target.value } })} /></Field>
            <Field label="Browser Headers JSON"><textarea rows="4" value={JSON.stringify(form.application.browser_headers ?? {}, null, 2)} onChange={(e) => { try { setForm({ ...form, application: { ...form.application, browser_headers: JSON.parse(e.target.value || '{}') } }) } catch { /* keep editing */ } }} /></Field>
          </section>
          <section className="panel">
            <h3>JIRA Configuration</h3>
            <Field label="Base URL"><input value={form.jira.base_url} onChange={(e) => setForm({ ...form, jira: { ...form.jira, base_url: e.target.value } })} /></Field>
            <Field label="Project Key"><input value={form.jira.project_key} onChange={(e) => setForm({ ...form, jira: { ...form.jira, project_key: e.target.value } })} /></Field>
            <Field label="Username"><input value={form.jira.username} onChange={(e) => setForm({ ...form, jira: { ...form.jira, username: e.target.value } })} /></Field>
            <Field label="API Token"><input type="password" value={form.jira.api_token} onChange={(e) => setForm({ ...form, jira: { ...form.jira, api_token: e.target.value } })} /></Field>
            <Field label="Story Issue Type"><input value={form.jira.issue_type} onChange={(e) => setForm({ ...form, jira: { ...form.jira, issue_type: e.target.value } })} /></Field>
            <Field label="Test Case Issue Type">
              <select className="journey-select" value={form.jira.test_case_issue_type} onChange={(e) => setForm({ ...form, jira: { ...form.jira, test_case_issue_type: e.target.value } })}>
                {TEST_CASE_ISSUE_TYPES.map((issueType) => <option key={issueType} value={issueType}>{issueType}</option>)}
              </select>
            </Field>
          </section>
          <section className="panel">
            <h3>AI / OpenAI Configuration</h3>
            <Field label="Provider"><input value={form.llm.provider} onChange={(e) => setForm({ ...form, llm: { ...form.llm, provider: e.target.value } })} /></Field>
            <Field label="Model">
              <select className="journey-select" value={form.llm.model} onChange={(e) => setForm({ ...form, llm: { ...form.llm, model: e.target.value } })}>
                {modelOptions.map((model) => (
                  <option key={`${model.provider}-${model.model}`} value={model.model}>{model.label}</option>
                ))}
              </select>
            </Field>
            <Field label="Supervisor Model"><input value={form.llm.supervisor_model} onChange={(e) => setForm({ ...form, llm: { ...form.llm, supervisor_model: e.target.value } })} /></Field>
            <Field label="API Endpoint"><input value={form.llm.api_endpoint} onChange={(e) => setForm({ ...form, llm: { ...form.llm, api_endpoint: e.target.value } })} /></Field>
            <Field label="Auth Token"><input type="password" value={form.llm.auth_token} onChange={(e) => setForm({ ...form, llm: { ...form.llm, auth_token: e.target.value } })} /></Field>
            <Field label="Browser Use Enabled"><select className="journey-select" value={String(form.llm.browser_use_enabled)} onChange={(e) => setForm({ ...form, llm: { ...form.llm, browser_use_enabled: e.target.value === 'true' } })}><option value="false">false</option><option value="true">true</option></select></Field>
            <Field label="Screenshot Timeout"><input type="number" min="1" step="0.5" value={form.llm.browser_timeout_screenshot} onChange={(e) => setForm({ ...form, llm: { ...form.llm, browser_timeout_screenshot: Number(e.target.value) } })} /></Field>
            <Field label="Navigate Timeout"><input type="number" min="1" step="0.5" value={form.llm.browser_timeout_navigate} onChange={(e) => setForm({ ...form, llm: { ...form.llm, browser_timeout_navigate: Number(e.target.value) } })} /></Field>
            <Field label="Temperature"><input type="number" min="0" max="2" step="0.1" value={form.llm.temperature} onChange={(e) => setForm({ ...form, llm: { ...form.llm, temperature: Number(e.target.value) } })} /></Field>
          </section>
        </div>
        <div className="inline-actions">
          <button type="submit">Save Configuration</button>
          <button type="button" className="secondary-button" onClick={testJira}>Test Jira Connection</button>
          <button type="button" className="secondary-button" onClick={testLLM}>Test LLM Connection</button>
          {message && <div className="notification-row"><Badge tone={message.includes('Failed') ? 'danger' : 'success'}>{message}</Badge></div>}
        </div>
      </form>
    </Card>
  )
}
