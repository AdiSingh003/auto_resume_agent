import React from 'react';
import StatusBadge, { PhaseChip } from './StatusBadge';
import { PIPELINE } from '../utils/agents';

export default function PipelineProgress({ trace, activeAgent, revisionHistory, maxRevisions }) {
  const completedRuns = {};
  const lastStatus = {};
  for (const ev of trace) {
    if (ev.status === 'running') continue;
    lastStatus[ev.agent] = ev.status;
    if (ev.status === 'completed') completedRuns[ev.agent] = (completedRuns[ev.agent] || 0) + 1;
  }
  const revisions = completedRuns['Replanner'] || 0;

  return (
    <div className="glass-panel animate-slide-in">
      <div className="progress-header">
        <div>
          <h2>Agents at work</h2>
          <p className="muted">
            LangGraph is running the pipeline. When a draft scores below threshold, the Replanner loops back to the
            Resume Drafter.
          </p>
        </div>
        <div className="loop-counter" title="Replanning loops taken">
          <span className="loop-value">{revisions}</span>
          <span className="muted small">of {maxRevisions} revisions</span>
        </div>
      </div>

      <ol className="stepper">
        {PIPELINE.map((step) => {
          const runs = completedRuns[step.agent] || 0;
          const state =
            step.agent === activeAgent ? 'running'
              : lastStatus[step.agent] === 'failed' ? 'failed'
                : runs ? 'completed' : 'pending';
          return (
            <li key={step.node} className={`step step-${state}`}>
              <StatusBadge status={state} iconOnly />
              <div className="step-body">
                <div className="step-title">
                  <strong>{step.agent}</strong>
                  <PhaseChip phase={step.phase} />
                  {runs > 1 && <span className="run-count" title="Times this agent ran">×{runs}</span>}
                </div>
                <div className="muted small">{step.description}</div>
              </div>
            </li>
          );
        })}
      </ol>

      {revisionHistory.length > 0 && (
        <p className="muted small" style={{ marginTop: '1rem' }}>
          Drafts evaluated so far: {revisionHistory.length}
        </p>
      )}
    </div>
  );
}
