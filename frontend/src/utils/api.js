// API client. Relative URLs go through the Vite dev-server proxy (vite.config.js),
// so the browser never makes cross-origin requests to the backend.
const API_BASE = '/api';

const wsUrl = (path) => {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocol}://${window.location.host}/ws${path}`;
};

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d) => d.msg).join('; ');
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new Error(detail);
  }
  return res;
}

export const api = {
  async getDemo() {
    return (await request('/demo')).json();
  },

  async generateResume({ jobDescription, candidateData = null, resumeText = null, useDemoProfile = false, templateStyle = 'modern' }) {
    const res = await request('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_description: jobDescription,
        candidate_data: candidateData,
        resume_text: resumeText,
        use_demo_profile: useDemoProfile,
        template_style: templateStyle,
      }),
    });
    return res.json();
  },

  async uploadResume(file) {
    const formData = new FormData();
    formData.append('file', file);
    return (await request('/upload/resume', { method: 'POST', body: formData })).json();
  },

  async getStatus(jobId) {
    return (await request(`/status/${jobId}`)).json();
  },

  async getReport(jobId) {
    return (await request(`/download/${jobId}/report`)).text();
  },

  resumeUrl(jobId, { version = null, inline = false } = {}) {
    const params = new URLSearchParams();
    if (version) params.set('version', version);
    if (inline) params.set('inline', 'true');
    const query = params.toString();
    return `${API_BASE}/download/${jobId}/resume${query ? `?${query}` : ''}`;
  },

  htmlPreviewUrl(jobId, version = null) {
    return `${API_BASE}/download/${jobId}/html${version ? `?version=${version}` : ''}`;
  },

  reportUrl(jobId) {
    return `${API_BASE}/download/${jobId}/report`;
  },
};

export const createWebSocket = (jobId, { onMessage, onClose }) => {
  const ws = new WebSocket(wsUrl(`/trace/${jobId}`));

  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch (e) {
      console.error('Failed to parse WebSocket message', e);
    }
  };
  ws.onclose = (event) => onClose?.(event);
  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };

  return ws;
};
