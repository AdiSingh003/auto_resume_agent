import React from 'react';
import { Target, Layout, ShieldCheck } from 'lucide-react';

const CircularProgress = ({ value, label, icon: Icon, color }) => {
  const radius = 30;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (value / 100) * circumference;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
      <div style={{ position: 'relative', width: '80px', height: '80px' }} role="img" aria-label={`${label}: ${value} out of 100`}>
        <svg style={{ transform: 'rotate(-90deg)', width: '100%', height: '100%' }}>
          <circle
            cx="40" cy="40" r={radius}
            fill="transparent" stroke="rgba(255,255,255,0.1)" strokeWidth="6"
          />
          <circle
            cx="40" cy="40" r={radius}
            fill="transparent" stroke={color} strokeWidth="6"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 1s ease-in-out' }}
          />
        </svg>
        <div style={{
          position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column'
        }}>
          <span style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-main)' }}>{value}</span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
        <Icon size={14} color={color} /> {label}
      </div>
    </div>
  );
};

const getColor = (score) => {
  if (score >= 80) return 'var(--success)';
  if (score >= 60) return 'var(--warning)';
  return 'var(--danger)';
};

export default function ScoreCard({ evaluation, status, draftsEvaluated, maxRevisions }) {
  if (!evaluation) return null;

  const revisionsUsed = Math.max(0, draftsEvaluated - 1);
  let banner;
  if (evaluation.passed) {
    banner = ['success', status === 'completed' ? 'All quality thresholds met ✓' : 'Thresholds met — verifying claims…'];
  } else if (status === 'completed') {
    banner = ['warning', `Finalized after ${revisionsUsed} revision${revisionsUsed === 1 ? '' : 's'} — some scores below threshold`];
  } else if (revisionsUsed >= maxRevisions) {
    banner = ['warning', 'Revision limit reached — finalizing…'];
  } else {
    banner = ['danger', `Below threshold — revising (round ${revisionsUsed + 1} of ${maxRevisions})…`];
  }

  const topIssues = (evaluation.feedback || [])
    .filter((fb) => fb.severity === 'critical' || fb.severity === 'high')
    .slice(0, 4);

  return (
    <div className="glass-panel animate-slide-in">
      <div className="panel-header">
        <h3>Evaluation Scores</h3>
        {draftsEvaluated > 0 && <span className="muted small">Draft v{draftsEvaluated}</span>}
      </div>

      <div className="gauges">
        <CircularProgress value={evaluation.ats_score} label="ATS Match" icon={Target} color={getColor(evaluation.ats_score)} />
        <CircularProgress value={evaluation.formatting_score} label="Formatting" icon={Layout} color={getColor(evaluation.formatting_score)} />
        <CircularProgress value={evaluation.factual_score} label="Factual" icon={ShieldCheck} color={getColor(evaluation.factual_score)} />
      </div>

      <div className={`score-banner ${banner[0]}`}>{banner[1]}</div>

      {topIssues.length > 0 && (
        <details className="trace-details" style={{ marginTop: '0.9rem' }}>
          <summary>Top issues found ({topIssues.length})</summary>
          <ul className="issue-list">
            {topIssues.map((fb, i) => (
              <li key={i} className={fb.severity}>
                <strong>{fb.category}</strong>: {fb.issue}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
