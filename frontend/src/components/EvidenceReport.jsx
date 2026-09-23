import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ShieldAlert, FileText } from 'lucide-react';
import { api } from '../utils/api';

// Split the report into collapsible sections at each "## " heading.
function splitSections(markdown) {
  const sections = [];
  let current = { title: 'Overview', lines: [] };
  // Raw HTML isn't rendered (the report is LLM output), but models often put <br> inside table cells.
  const text = markdown.replace(/<br\s*\/?>/gi, ' ');
  for (const line of text.split('\n')) {
    const heading = line.match(/^##\s+(.*)/);
    if (heading) {
      if (current.lines.join('').trim()) sections.push(current);
      current = { title: heading[1].replace(/[*_`]/g, '').trim(), lines: [] };
    } else {
      current.lines.push(line);
    }
  }
  if (current.lines.join('').trim()) sections.push(current);
  return sections.map((s) => ({ title: s.title, body: s.lines.join('\n').trim() }));
}

function VerificationSummary({ verification: v }) {
  const clean = v.trustworthy && !v.fabrication_detected;
  return (
    <div className={`verification ${clean ? '' : 'warn'}`}>
      <div className="verification-stats">
        <div>
          <span className="stat">{v.verified_claims}/{v.total_claims}</span>
          <span className="muted small">claims verified</span>
        </div>
        <div>
          <span className="stat">{v.removed_claims.length}</span>
          <span className="muted small">unsupported items removed</span>
        </div>
        <div>
          <span className="stat">{v.fabrication_detected ? 'Yes' : 'No'}</span>
          <span className="muted small">fabrication found before removal</span>
        </div>
      </div>

      {v.removed_claims.length > 0 && (
        <div>
          <div className="small strong">Removed from the final resume</div>
          <ul className="claim-list">
            {v.removed_claims.map((claim, i) => <li key={i} className="removed">{claim}</li>)}
          </ul>
        </div>
      )}

      {v.unverified_claims.length > 0 && (
        <details className="trace-details">
          <summary>Verifier notes ({v.unverified_claims.length} flagged)</summary>
          <ul className="claim-list">
            {v.unverified_claims.map((c, i) => (
              <li key={i}>
                <q>{c.claim}</q> — <span className="muted">{c.notes || c.evidence_source}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export default function EvidenceReport({ jobId, verification }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api.getReport(jobId)
      .then((text) => !cancelled && setReport(text))
      .catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [jobId]);

  const sections = useMemo(() => (report ? splitSections(report) : []), [report]);

  return (
    <div className="glass-panel animate-slide-in">
      <div className="panel-header">
        <ShieldAlert size={18} color="var(--accent)" />
        <h3>Evidence &amp; Change Report</h3>
        <a href={api.reportUrl(jobId)} download className="btn btn-outline btn-sm">
          <FileText size={16} /> Download .md
        </a>
      </div>

      {verification && <VerificationSummary verification={verification} />}

      {error && <p className="error-text">Report unavailable: {error}</p>}
      {!report && !error && <p className="muted">Loading report…</p>}

      {sections.map((section, i) => (
        <details key={`${i}-${section.title}`} className="report-section" open={i === 0}>
          <summary>{section.title}</summary>
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{section.body}</ReactMarkdown>
          </div>
        </details>
      ))}
    </div>
  );
}
