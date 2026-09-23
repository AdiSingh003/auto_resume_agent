import React from 'react';
import { GitBranch } from 'lucide-react';
import { api } from '../utils/api';

function DraftChanges({ changes }) {
  const added = changes.added || [];
  const removed = changes.removed || [];
  const skillsAdded = changes.skills_added || [];
  const skillsRemoved = changes.skills_removed || [];
  if (!added.length && !removed.length && !skillsAdded.length && !skillsRemoved.length && !changes.summary_changed) {
    return <div className="muted small">No content changes from previous draft</div>;
  }

  return (
    <details className="diff">
      <summary>
        {added.length} bullet{added.length === 1 ? '' : 's'} added · {removed.length} removed
        {changes.summary_changed ? ' · summary rewritten' : ''}
      </summary>
      {removed.map((line, i) => <div key={`r${i}`} className="diff-line removed">{line}</div>)}
      {added.map((line, i) => <div key={`a${i}`} className="diff-line added">{line}</div>)}
      {skillsRemoved.length > 0 && <div className="diff-line removed">Skills: {skillsRemoved.join(', ')}</div>}
      {skillsAdded.length > 0 && <div className="diff-line added">Skills: {skillsAdded.join(', ')}</div>}
    </details>
  );
}

export default function RevisionHistory({ jobId, history, finalPdf, completed, selectedVersion, onSelect }) {
  if (!history.length) return null;
  const verifierEdited = finalPdf === 'resume_final.pdf';

  return (
    <div className="glass-panel animate-slide-in">
      <div className="panel-header">
        <GitBranch size={18} color="var(--accent)" />
        <h3>Revision History</h3>
      </div>

      <ol className="revision-list">
        {history.map((entry, i) => {
          const previous = history[i - 1];
          const delta = previous ? entry.overall_score - previous.overall_score : null;
          const isFinal = completed && !verifierEdited && i === history.length - 1;
          const selected = selectedVersion === entry.version || (isFinal && selectedVersion == null);
          return (
            <li key={entry.version} className={`revision ${selected ? 'selected' : ''}`}>
              <div className="revision-head">
                <strong>Draft v{entry.version}{isFinal ? ' (final)' : ''}</strong>
                {delta !== null && (
                  <span className={`delta ${delta >= 0 ? 'up' : 'down'}`}>{delta >= 0 ? '+' : ''}{delta}</span>
                )}
                <span className={`score-pill ${entry.passed ? 'ok' : 'low'}`} title="Overall score">{entry.overall_score}</span>
              </div>
              <div className="muted small">
                ATS {entry.ats_score} · Format {entry.formatting_score} · Factual {entry.factual_score}
                {entry.pages ? ` · ${entry.pages} page${entry.pages === 1 ? '' : 's'}` : ''}
              </div>
              {i === 0 ? <div className="muted small">Initial draft</div> : <DraftChanges changes={entry.changes || {}} />}
              {onSelect && (
                <div className="revision-actions">
                  <button className="btn-link" onClick={() => onSelect(isFinal ? null : entry.version)}>Preview</button>
                  <a className="btn-link" href={api.resumeUrl(jobId, { version: entry.version })} download>PDF</a>
                </div>
              )}
            </li>
          );
        })}

        {completed && verifierEdited && (
          <li className={`revision ${selectedVersion == null ? 'selected' : ''}`}>
            <div className="revision-head">
              <strong>Final (verified)</strong>
            </div>
            <div className="muted small">Last draft with unsupported claims removed by the Final Verifier</div>
            {onSelect && (
              <div className="revision-actions">
                <button className="btn-link" onClick={() => onSelect(null)}>Preview</button>
                <a className="btn-link" href={api.resumeUrl(jobId)} download>PDF</a>
              </div>
            )}
          </li>
        )}
      </ol>
    </div>
  );
}
