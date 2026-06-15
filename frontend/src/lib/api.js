const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  getScenarios: () => request('/scenarios'),
  getWorklist: () => request('/worklist'),

  createSession: (data) =>
    request('/sessions', { method: 'POST', body: JSON.stringify(data) }),
  getSession: (id) => request(`/sessions/${id}`),
  getSessionState: (id) => request(`/sessions/${id}/state`),

  sendMessage: (sessionId, message) =>
    request(`/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  getMessages: (sessionId) => request(`/sessions/${sessionId}/messages`),

  getSymptoms: (sessionId) => request(`/sessions/${sessionId}/symptoms`),
  getVitals: (sessionId) => request(`/sessions/${sessionId}/vitals`),
  getMeds: (sessionId) => request(`/sessions/${sessionId}/meds`),
  getAlerts: (sessionId) => request(`/sessions/${sessionId}/alerts`),
  getRiskScores: (sessionId) => request(`/sessions/${sessionId}/risk-scores`),
  getConclusion: (sessionId) => request(`/sessions/${sessionId}/conclusion`),

  resetDb: () => request('/reset-db', { method: 'POST' }),
};
