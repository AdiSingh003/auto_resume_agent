import React, { useState } from 'react';
import { api } from '../utils/api';

export default function ResumePreview({ jobId, version = null, title, defaultMode = 'pdf', height = 900 }) {
  const [mode, setMode] = useState(defaultMode);
  const src = mode === 'pdf'
    ? `${api.resumeUrl(jobId, { version, inline: true })}#view=FitH`
    : api.htmlPreviewUrl(jobId, version);

  return (
    <div className="glass-panel preview-panel animate-slide-in">
      <div className="preview-toolbar">
        <strong>{title}</strong>
        <div className="tabs" role="tablist" aria-label="Preview format">
          {['pdf', 'html'].map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              className={`tab ${mode === m ? 'active' : ''}`}
              onClick={() => setMode(m)}
            >
              {m.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      <iframe key={src} src={src} title="Resume preview" className="preview-frame" style={{ height }} />
    </div>
  );
}
