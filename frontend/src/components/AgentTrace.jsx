import React, { useEffect, useRef } from 'react';
import { Activity } from 'lucide-react';
import StatusBadge, { PhaseChip } from './StatusBadge';
import { PHASE_BY_AGENT } from '../utils/agents';

const formatDuration = (ms) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`);

export default function AgentTrace({ events, activeAgent, status }) {
  const containerRef = useRef(null);
  // "running" events are superseded by the live active-agent row and the later completed event.
  const finished = events.filter((ev) => ev.status !== 'running');
  const showActive = status === 'generating' && activeAgent;

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [finished.length, activeAgent]);

  return (
    <div className="glass-panel trace-panel">
      <div className="panel-header">
        <Activity size={18} color="var(--primary)" />
        <h3>Live Agent Trace</h3>
        <span className="muted small">{finished.length} steps</span>
      </div>

      <div ref={containerRef} className="trace-list" aria-live="polite">
        {finished.length === 0 && !showActive && (
          <div className="muted empty">Waiting for agents to start...</div>
        )}

        {finished.map((ev) => (
          <div key={ev.seq} className="trace-event">
            <StatusBadge status={ev.status} iconOnly />
            <div className="trace-body">
              <div className="trace-title">
                <strong>{ev.agent}</strong>
                <PhaseChip phase={PHASE_BY_AGENT[ev.agent]} />
                {ev.duration_ms != null && <span className="muted small">{formatDuration(ev.duration_ms)}</span>}
              </div>
              <div className="trace-message">{ev.message}</div>
              {ev.details && Object.keys(ev.details).length > 0 && (
                <details className="trace-details">
                  <summary>Details</summary>
                  <pre>{JSON.stringify(ev.details, null, 2)}</pre>
                </details>
              )}
            </div>
          </div>
        ))}

        {showActive && (
          <div className="trace-event active">
            <StatusBadge status="running" iconOnly />
            <div className="trace-body">
              <div className="trace-title">
                <strong>{activeAgent}</strong>
                <PhaseChip phase={PHASE_BY_AGENT[activeAgent]} />
              </div>
              <div className="trace-message">Working…</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
