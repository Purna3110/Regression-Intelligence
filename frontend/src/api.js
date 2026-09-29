const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

async function request(path, options = {}) {
  let response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new Error(`Could not reach the Regression Intelligence API at ${API_BASE_URL}.`)
  }

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload.detail === 'string' ? payload.detail : `Request failed (${response.status}).`
    throw new Error(detail)
  }

  return payload
}

export function checkApiHealth() {
  return request('/api/health')
}

export function recallDefects(payload) {
  return request('/api/regression/recall', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function reflectOnRegression(payload) {
  return request('/api/regression/reflect', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function retainDefect(payload) {
  return request('/api/memory/defects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}