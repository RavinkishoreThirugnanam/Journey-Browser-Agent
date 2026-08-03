import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Badge, Card, Field } from '../components/Ui'

const DEFAULT_MODELS = [
  { provider: 'OpenAI', model: 'gpt-4o-mini', label: 'GPT-4o mini' },
  { provider: 'OpenAI', model: 'gpt-4.1-mini', label: 'GPT-4.1 mini' },
  { provider: 'OpenAI', model: 'gpt-4.1', label: 'GPT-4.1' },
  { provider: 'OpenAI', model: 'gpt-5', label: 'GPT-5' },
  { provider: 'Google Gemini', model: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
  { provider: 'Google Gemini', model: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
]

const TEST_CASE_ISSUE_TYPES = ['Test', 'Task', 'Story', 'Bug']
const LLM_PROVIDERS = ['OpenAI', 'Google Gemini']

export function ConfigurationPage() {
  const [modelCatalog, setModelCatalog] = useState(DEFAULT_MODELS)
  const [form, setForm] = useState({ jira: { base_url: '', project_key: '', username: '', api_token: '', auth_type: 'basic', issue_type: 'Story', test_case_issue_type: 'Test' }, llm: { provider: 'OpenAI', model: 'gpt-4o-mini', supervisor_model: 'gpt-4o-mini', api_endpoint: '', auth_token: '', temperature: 0.2, browser_timeout_screenshot: 30.0, browser_timeout_navigate: 30.0, browser_use_enabled: true }, application: { base_url: '', environment: 'development', default_project: '', global_parameters: {}, browser_headers: {}, default_follow_links: true } })
  const [message, setMessage] = useState('')
  const [configLoading, setConfigLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getLLMModels().then((payload) => {
      if (Array.isArray(payload.models) && payload.models.length) setModelCatalog(payload.models)
    }).catch(() => {})
  }, [])

  const applyConfiguration = (config) => {
    setForm((current) => ({
      jira: { ...current.jira, ...(config?.jira ?? {}) },
      llm: { ...current.llm, ...(config?.llm ?? {}) },
      application: { ...current.application, ...(config?.application ?? {}) },
    }))
  }

  const load = async () => {
    try {
      applyConfiguration(await api.getConfiguration())
    } catch (error) {
      setMessage(error?.message || 'Unable to load the saved configuration.')
    } finally {
      setConfigLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setMessage('')
    try {
      const result = await api.saveConfiguration(form)
      const persisted = await api.getConfiguration().catch(() => result.configuration)
      applyConfiguration(persisted || result.configuration)
      setMessage('Configuration saved and verified. These settings will be reused automatically.')
    } catch (error) {
      setMessage(error?.message || 'Failed to save configuration.')
    } finally {
      setSaving(false)
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
    } catch (error) {
      let message = error?.message || 'LLM validation failed.'
      try {
        const payload = JSON.parse(message)
        message = payload.detail || payload.message || message
      } catch {}
      setMessage(message)
    }
  }

  const modelOptions = useMemo(() => modelCatalog.filter((model) => model.provider === form.llm.provider), [modelCatalog, form.llm.provider])
  useEffect(() => {
    if (!form.llm.model) {
      const firstModel = modelCatalog.find((item) => item.provider === form.llm.provider)
      if (firstModel) setForm((current) => ({ ...current, llm: { ...current.llm, model: firstModel.model, supervisor_model: current.llm.supervisor_model || firstModel.model } }))
    }
  }, [modelCatalog, form.llm.provider, form.llm.model])
  const selectProvider = (provider) => {
    const firstModel = modelCatalog.find((item) => item.provider === provider)
    const endpoint = provider === 'Google Gemini' ? 'https://generativelanguage.googleapis.com/v1beta' : 'https://api.openai.com/v1'
    setForm({ ...form, llm: { ...form.llm, provider, model: firstModel?.model ?? '', supervisor_model: firstModel?.model ?? '', api_endpoint: endpoint } })
  }

  if (configLoading) {
    return (
      <Card title="Configuration Settings" subtitle="Loading your saved settings.">
        <div className="page-loading">Loading saved configuration...</div>
      </Card>
    )
  }

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
            <label className="field checkbox-field checkbox-clickable config-follow-links-field">
              <span><strong>Default Follow Links</strong><small>Follow same-site links by default when creating journey maps.</small></span>
              <input type="checkbox" checked={form.application.default_follow_links !== false} onChange={(e) => setForm({ ...form, application: { ...form.application, default_follow_links: e.target.checked } })} />
            </label>
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
            <h3>AI / LLM Configuration</h3>
            <Field label="Provider"><select className="journey-select" value={form.llm.provider} onChange={(e) => selectProvider(e.target.value)}>{LLM_PROVIDERS.map((provider) => <option key={provider} value={provider}>{provider}</option>)}</select></Field>
            <Field label="Model">
              <select className="journey-select" value={form.llm.model} onChange={(e) => setForm({ ...form, llm: { ...form.llm, model: e.target.value } })}>
                {(modelOptions.length ? modelOptions : [{ provider: form.llm.provider, model: form.llm.model, label: form.llm.model }]).map((model) => (
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
          <button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save Configuration'}</button>
          <button type="button" className="secondary-button" onClick={testJira} disabled={saving}>Test Jira Connection</button>
          <button type="button" className="secondary-button" onClick={testLLM} disabled={saving}>Test LLM Connection</button>
          {message && <div className="notification-row"><Badge tone={/(failed|unable|error)/i.test(message) ? 'danger' : 'success'}>{message}</Badge></div>}
        </div>
      </form>
    </Card>
  )
}
