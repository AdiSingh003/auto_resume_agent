import React from 'react';
import { CheckCircle, XCircle, Clock, RefreshCw } from 'lucide-react';
import { PHASE_COLORS } from '../utils/agents';

const STATUS_STYLES = {
  running: { label: 'Running', color: 'var(--primary)', Icon: RefreshCw, spin: true },
  completed: { label: 'Done', color: 'var(--success)', Icon: CheckCircle },
  failed: { label: 'Failed', color: 'var(--danger)', Icon: XCircle },
  pending: { label: 'Pending', color: 'var(--text-muted)', Icon: Clock },
};

export default function StatusBadge({ status = 'pending', iconOnly = false }) {
  const { label, color, Icon, spin } = STATUS_STYLES[status] || STATUS_STYLES.pending;
  const iconClass = spin ? 'spin' : undefined;

  if (iconOnly) {
    return <Icon size={16} color={color} className={iconClass} aria-label={label} />;
  }
  return (
    <span className="status-badge" style={{ color, borderColor: color }}>
      <Icon size={12} className={iconClass} /> {label}
    </span>
  );
}

export function PhaseChip({ phase }) {
  if (!phase) return null;
  return (
    <span className="phase-chip" style={{ color: PHASE_COLORS[phase] }}>
      {phase}
    </span>
  );
}
