// The LangGraph pipeline as the UI presents it. `agent` matches the backend's trace agent_name,
// `phase` maps each agent onto the Goal → Decision → Action → Result → Adaptation → Outcome loop.
export const PIPELINE = [
  { node: 'parse_jd', agent: 'JD Parser', phase: 'Goal', description: 'Extract requirements and ATS keywords' },
  { node: 'research_role', agent: 'Role Researcher', phase: 'Goal', description: 'Research the role and company on the web' },
  { node: 'analyze_profile', agent: 'Profile Analyzer', phase: 'Goal', description: 'Structure the candidate’s evidence' },
  { node: 'map_evidence', agent: 'Evidence Mapper', phase: 'Decision', description: 'Match evidence to requirements, find gaps' },
  { node: 'draft_resume', agent: 'Resume Drafter', phase: 'Action', description: 'Draft or revise the tailored resume' },
  { node: 'render_pdf', agent: 'PDF Renderer', phase: 'Action', description: 'Render the draft to PDF' },
  { node: 'evaluate', agent: 'Multi-Evaluator', phase: 'Result', description: 'Score ATS, formatting, factual consistency' },
  { node: 'revise', agent: 'Replanner', phase: 'Adaptation', description: 'Plan targeted fixes, loop back to the Drafter' },
  { node: 'verify', agent: 'Final Verifier', phase: 'Outcome', description: 'Verify claims, remove unsupported ones' },
  { node: 'report', agent: 'Report Generator', phase: 'Outcome', description: 'Write the evidence and change report' },
];

export const PHASE_BY_AGENT = Object.fromEntries(PIPELINE.map((step) => [step.agent, step.phase]));

export const PHASE_COLORS = {
  Goal: '#60a5fa',
  Decision: '#22d3ee',
  Action: '#a78bfa',
  Result: '#fbbf24',
  Adaptation: '#f472b6',
  Outcome: '#34d399',
};
