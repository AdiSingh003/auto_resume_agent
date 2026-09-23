import React, { useCallback, useEffect, useReducer, useState } from 'react';
import { Download, FileText } from 'lucide-react';
import { api, createWebSocket } from './utils/api';
import Header from './components/Header';
import UploadPanel from './components/UploadPanel';
import AgentTrace from './components/AgentTrace';
import PipelineProgress from './components/PipelineProgress';
import ScoreCard from './components/ScoreCard';
import RevisionHistory from './components/RevisionHistory';
import ResumePreview from './components/ResumePreview';
import EvidenceReport from './components/EvidenceReport';
import './index.css';

const initialJob = {
  jobId: null,
  status: 'idle', // idle, generating, completed, error
  trace: [],
  activeAgent: null,
  evaluation: null,
  verification: null,
  revisionHistory: [],
  maxRevisions: 0,
  finalPdf: null,
  error: '',
};

// Trace events carry a `seq` (index in the job's trace). The WebSocket snapshot and live
// events can overlap, so merge by seq instead of appending.
function mergeTrace(existing, incoming) {
  const bySeq = new Map(existing.map((ev) => [ev.seq, ev]));
  for (const ev of incoming) bySeq.set(ev.seq, ev);
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
}

function applySnapshot(state, snapshot) {
  const terminal = state.status === 'completed' || state.status === 'error';
  const status = snapshot.status === 'completed' ? 'completed'
    : snapshot.status === 'failed' ? 'error'
      : terminal ? state.status : 'generating';
  return {
    ...state,
    status,
    trace: mergeTrace(state.trace, snapshot.trace || []),
    activeAgent: status === 'generating' ? snapshot.active_agent : null,
    evaluation: snapshot.evaluation || state.evaluation,
    verification: snapshot.verification || state.verification,
    revisionHistory: snapshot.revision_history?.length ? snapshot.revision_history : state.revisionHistory,
    maxRevisions: snapshot.max_revisions ?? state.maxRevisions,
    finalPdf: snapshot.final_pdf ?? state.finalPdf,
    error: snapshot.error || state.error,
  };
}

function jobReducer(state, action) {
  switch (action.type) {
    case 'start':
      return { ...initialJob, status: 'generating' };
    case 'started':
      return { ...state, jobId: action.jobId };
    case 'snapshot':
      return applySnapshot(state, action.snapshot);
    case 'agent_start':
      return { ...state, activeAgent: action.agent };
    case 'trace': {
      const finishedActive = action.event.agent === state.activeAgent && action.event.status !== 'running';
      return {
        ...state,
        trace: mergeTrace(state.trace, [action.event]),
        activeAgent: finishedActive ? null : state.activeAgent,
      };
    }
    case 'evaluation':
      return {
        ...state,
        evaluation: action.evaluation,
        revisionHistory: action.evaluation.revision_history || state.revisionHistory,
      };
    case 'error':
      return { ...state, status: 'error', activeAgent: null, error: action.message };
    case 'reset':
      return initialJob;
    default:
      return state;
  }
}

function App() {
  const [job, dispatch] = useReducer(jobReducer, initialJob);
  const [previewVersion, setPreviewVersion] = useState(null);

  // Live updates over WebSocket; fall back to polling if the socket drops mid-run.
  useEffect(() => {
    if (!job.jobId || job.status !== 'generating') return;

    let closedByUs = false;
    let pollTimer = null;
    const poll = async () => {
      try {
        dispatch({ type: 'snapshot', snapshot: await api.getStatus(job.jobId) });
      } catch (e) {
        console.warn('Status poll failed', e);
      }
    };

    const ws = createWebSocket(job.jobId, {
      onMessage: (msg) => {
        switch (msg.type) {
          case 'snapshot':
          case 'complete':
            dispatch({ type: 'snapshot', snapshot: msg });
            break;
          case 'agent_start':
            dispatch({ type: 'agent_start', agent: msg.agent });
            break;
          case 'trace':
            dispatch({ type: 'trace', event: msg });
            break;
          case 'evaluation':
            dispatch({ type: 'evaluation', evaluation: msg });
            break;
          case 'error':
            dispatch({ type: 'error', message: msg.message });
            break;
          default:
            break;
        }
      },
      onClose: () => {
        if (!closedByUs) pollTimer = setInterval(poll, 2000);
      },
    });

    return () => {
      closedByUs = true;
      ws.close();
      clearInterval(pollTimer);
    };
  }, [job.jobId, job.status]);

  const handleStart = useCallback(async (payload) => {
    dispatch({ type: 'start' });
    setPreviewVersion(null);
    try {
      const res = await api.generateResume(payload);
      dispatch({ type: 'started', jobId: res.job_id });
    } catch (err) {
      dispatch({ type: 'error', message: err.message });
    }
  }, []);

  const handleReset = useCallback(() => {
    dispatch({ type: 'reset' });
    setPreviewVersion(null);
  }, []);

  const latestDraft = job.revisionHistory[job.revisionHistory.length - 1];
  const showWorkspace = job.jobId && (job.status !== 'error' || job.trace.length > 0);

  return (
    <div className="app-container">
      <Header onNewResume={handleReset} />

      <main className="app-main">
        {job.status === 'idle' && <UploadPanel onStart={handleStart} />}

        {job.status === 'error' && (
          <div className="glass-panel error-panel" role="alert">
            <h3>Error Generating Resume</h3>
            <p>{job.error}</p>
            <button className="btn btn-outline" style={{ marginTop: '1rem' }} onClick={handleReset}>
              Try Again
            </button>
          </div>
        )}

        {job.status === 'generating' && !job.jobId && (
          <div className="glass-panel muted">Starting agents…</div>
        )}

        {showWorkspace && job.status !== 'idle' && (
          <div className="workspace">
            <div className="main-column">
              {job.status === 'completed' ? (
                <>
                  <div className="result-header">
                    <div>
                      <h2>Final Resume</h2>
                      <p className="muted small">
                        {job.revisionHistory.length} draft{job.revisionHistory.length === 1 ? '' : 's'} evaluated
                        {job.verification ? ` · ${job.verification.verified_claims}/${job.verification.total_claims} claims verified` : ''}
                      </p>
                    </div>
                    <div className="result-actions">
                      <a href={api.resumeUrl(job.jobId)} download className="btn btn-primary">
                        <Download size={18} /> Download PDF
                      </a>
                      <a href={api.reportUrl(job.jobId)} download className="btn btn-outline">
                        <FileText size={18} /> Report
                      </a>
                    </div>
                  </div>
                  <ResumePreview
                    key="final-preview"
                    jobId={job.jobId}
                    version={previewVersion}
                    title={previewVersion ? `Draft v${previewVersion}` : 'Final resume'}
                  />
                  <EvidenceReport jobId={job.jobId} verification={job.verification} />
                </>
              ) : (
                <>
                  <PipelineProgress
                    trace={job.trace}
                    activeAgent={job.activeAgent}
                    revisionHistory={job.revisionHistory}
                    maxRevisions={job.maxRevisions}
                  />
                  {latestDraft?.pdf_file && (
                    <ResumePreview
                      key="draft-preview"
                      jobId={job.jobId}
                      version={latestDraft.version}
                      defaultMode="html"
                      height={700}
                      title={`Latest draft (v${latestDraft.version}) — work in progress`}
                    />
                  )}
                </>
              )}
            </div>

            <aside className="sidebar">
              <AgentTrace events={job.trace} activeAgent={job.activeAgent} status={job.status} />
              {job.evaluation && (
                <ScoreCard
                  evaluation={job.evaluation}
                  status={job.status}
                  draftsEvaluated={job.revisionHistory.length}
                  maxRevisions={job.maxRevisions}
                />
              )}
              <RevisionHistory
                jobId={job.jobId}
                history={job.revisionHistory}
                finalPdf={job.finalPdf}
                completed={job.status === 'completed'}
                selectedVersion={previewVersion}
                onSelect={job.status === 'completed' ? setPreviewVersion : null}
              />
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
