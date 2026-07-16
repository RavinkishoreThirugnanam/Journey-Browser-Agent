import mermaid from 'mermaid'

mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    primaryColor: '#ff6600',
    primaryTextColor: '#333333',
    primaryBorderColor: '#333366',
    lineColor: '#333366',
    secondaryColor: '#f5f5f5',
    tertiaryColor: '#ffffff',
    background: '#ffffff',
    mainBkg: '#ffffff',
    secondaryBkg: '#f5f5f5',
    tertiaryBkg: '#ffffff',
    fontFamily: 'Inter, system-ui, sans-serif',
    fontSize: '16px',
  },
})

export async function renderMermaid(svgId, code) {
  const result = await mermaid.render(svgId, code)
  return result.svg
}
