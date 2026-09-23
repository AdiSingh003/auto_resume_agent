import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Upload, Briefcase, FileJson, Play, User, FileText } from 'lucide-react';
import { api } from '../utils/api';

const SOURCES = [
  { id: 'demo', label: 'Demo profile', Icon: User },
  { id: 'upload', label: 'Upload resume', Icon: Upload },
  { id: 'paste', label: 'Paste text / JSON', Icon: FileJson },
];

const TEMPLATES = [
  { id: 'modern', label: 'Modern' },
  { id: 'minimal', label: 'Minimal' },
];

export default function UploadPanel({ onStart }) {
  const [jd, setJd] = useState('');
  const [source, setSource] = useState('demo');
  const [demo, setDemo] = useState(null);
  const [uploaded, setUploaded] = useState(null); // { filename, text, characters }
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [pasted, setPasted] = useState('');
  const [templateStyle, setTemplateStyle] = useState('modern');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    api.getDemo().then(setDemo).catch(() => {});
  }, []);

  const loadDemo = async () => {
    setError('');
    try {
      const data = demo || (await api.getDemo());
      setDemo(data);
      setJd(data.job_description);
      setSource('demo');
    } catch (e) {
      setError(`Could not load demo data: ${e.message}`);
    }
  };

  const handleFile = async (file) => {
    if (!file) return;
    setError('');
    setUploaded(null);
    setUploading(true);
    try {
      setUploaded(await api.uploadResume(file));
    } catch (e) {
      setError(`Upload failed: ${e.message}`);
    } finally {
      setUploading(false);
    }
  };

  const pastedJson = useMemo(() => {
    try {
      const value = JSON.parse(pasted);
      return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
    } catch {
      return null;
    }
  }, [pasted]);

  const candidateReady =
    source === 'demo'
    || (source === 'upload' && uploaded?.text?.trim())
    || (source === 'paste' && pasted.trim());
  const canStart = Boolean(jd.trim() && candidateReady && !uploading && !submitting);

  const handleStart = async () => {
    const payload = { jobDescription: jd, templateStyle };
    if (source === 'demo') payload.useDemoProfile = true;
    else if (source === 'upload') payload.resumeText = uploaded.text;
    else if (pastedJson) payload.candidateData = pastedJson;
    else payload.resumeText = pasted;

    setError('');
    setSubmitting(true);
    try {
      await onStart(payload);
    } finally {
      setSubmitting(false);
    }
  };

  const openFilePicker = () => fileInputRef.current?.click();
  const candidate = demo?.candidate;

  return (
    <div className="glass-panel animate-slide-in upload-panel">
      <div style={{ textAlign: 'center' }}>
        <h2>Generate a Tailored Resume</h2>
        <p className="muted">The autonomous agent will analyze the JD, map your evidence, and draft a verified PDF.</p>
      </div>

      <section>
        <div className="field-label-row">
          <label htmlFor="job-description" className="field-label">
            <Briefcase size={18} color="var(--primary)" /> Target Job Description
          </label>
          <button className="btn btn-outline btn-sm" onClick={loadDemo}>
            Load Demo JD &amp; Profile
          </button>
        </div>
        <textarea
          id="job-description"
          rows={9}
          placeholder="Paste the job description here..."
          value={jd}
          onChange={(e) => setJd(e.target.value)}
        />
      </section>

      <section>
        <div className="field-label">
          <User size={18} color="var(--accent)" /> Candidate Data Source
        </div>
        <div className="tabs" role="tablist" aria-label="Candidate data source">
          {SOURCES.map(({ id, label, Icon }) => (
            <button
              key={id}
              role="tab"
              aria-selected={source === id}
              className={`tab ${source === id ? 'active' : ''}`}
              onClick={() => setSource(id)}
            >
              <Icon size={15} /> {label}
            </button>
          ))}
        </div>

        {source === 'demo' && (
          <div className="info-box">
            {candidate ? (
              <>
                Using the bundled profile for <strong>{candidate.name}</strong>
                {candidate.experience?.[0] ? ` — ${candidate.experience[0].title}` : ''}: {candidate.skills.length} skills,{' '}
                {candidate.experience.length} roles, {candidate.projects.length} project(s).
              </>
            ) : (
              'Using the bundled sample_candidate.json profile.'
            )}
          </div>
        )}

        {source === 'upload' && (
          <>
            <div
              className={`dropzone ${dragOver ? 'drag-over' : ''}`}
              role="button"
              tabIndex={0}
              onClick={openFilePicker}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && openFilePicker()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
            >
              <Upload size={28} />
              <div>
                {uploading ? 'Extracting text…'
                  : uploaded ? <>✓ <strong>{uploaded.filename}</strong> — {uploaded.characters.toLocaleString()} characters extracted</>
                    : <>Drag &amp; drop your resume here, or <u>browse</u></>}
              </div>
              <div className="muted small">PDF, DOCX or TXT · max 10 MB</div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt"
                hidden
                data-testid="resume-file-input"
                onChange={(e) => { handleFile(e.target.files[0]); e.target.value = ''; }}
              />
            </div>
            {uploaded && (
              <details className="extracted">
                <summary className="small">Review / edit extracted text</summary>
                <textarea
                  rows={8}
                  value={uploaded.text}
                  onChange={(e) => setUploaded({ ...uploaded, text: e.target.value })}
                />
              </details>
            )}
          </>
        )}

        {source === 'paste' && (
          <>
            <textarea
              rows={8}
              style={{ marginTop: '0.75rem' }}
              placeholder='Paste resume text, or a JSON profile like {"name": "...", "skills": [], "experience": []}'
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
            />
            <div className="muted small" style={{ marginTop: '0.4rem' }}>
              {!pasted.trim() ? 'Plain text is parsed by the Profile Analyzer agent; JSON is used as structured data.'
                : pastedJson ? 'Detected a structured JSON profile.' : 'Will be parsed as plain resume text.'}
            </div>
          </>
        )}
      </section>

      <section>
        <div className="field-label">
          <FileText size={18} color="var(--success)" /> Resume Template
        </div>
        <div className="tabs" role="tablist" aria-label="Resume template">
          {TEMPLATES.map(({ id, label }) => (
            <button
              key={id}
              role="tab"
              aria-selected={templateStyle === id}
              className={`tab ${templateStyle === id ? 'active' : ''}`}
              onClick={() => setTemplateStyle(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      {error && <div className="error-text" role="alert">{error}</div>}

      <button className="btn btn-primary btn-block" onClick={handleStart} disabled={!canStart}>
        <Play size={20} />
        {submitting ? 'Starting agents…' : 'Start Autonomous Pipeline'}
      </button>
    </div>
  );
}
