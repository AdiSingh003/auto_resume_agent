"""End-to-end pipeline run against the real LLM providers (no web server).

Usage: python test_e2e.py
"""

import asyncio
import json
import os
import sys

# Ensure backend modules can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.agents.graph import agent_graph, recursion_limit_for
from backend.agents.state import new_state
from backend.api.routes import load_demo_candidate, load_demo_job_description

JOB_ID = "test_job_123"
MAX_REVISIONS = 2  # Keep it low for fast testing


async def test_pipeline():
    print("Starting end-to-end test...", flush=True)

    state = new_state(
        job_id=JOB_ID,
        job_description=load_demo_job_description(),
        candidate_data=load_demo_candidate(),
        max_revisions=MAX_REVISIONS,
    )

    final_state = dict(state)
    print("\nRunning LangGraph agent pipeline...", flush=True)
    async for event in agent_graph.astream(
        state, config={"recursion_limit": recursion_limit_for(MAX_REVISIONS)}, stream_mode="updates"
    ):
        for node, state_update in event.items():
            print(f"[done] {node}", flush=True)
            for trace in state_update.get("trace", []):
                if trace.status.value != "running":
                    print(f"  -> {trace.agent_name}: {trace.message}", flush=True)
            final_state.update({k: v for k, v in state_update.items() if k != "trace"})

    assert final_state.get("current_agent") == "done", f"Pipeline stopped early: {final_state.get('error')}"
    assert final_state.get("pdf_path") and os.path.exists(final_state["pdf_path"]), "Final PDF missing"
    assert final_state.get("evidence_report"), "Evidence report missing"

    print("\nPipeline completed successfully!")
    print(f"Final PDF: {final_state['pdf_path']}")
    print("Revision history:")
    print(json.dumps(
        [{k: v for k, v in entry.items() if k != "changes"} for entry in final_state["revision_history"]],
        indent=2,
    ))
    verification = final_state.get("verification")
    if verification:
        print(f"Verified {verification.verified_claims}/{verification.total_claims} claims; "
              f"removed: {verification.removed_claims}")


if __name__ == "__main__":
    asyncio.run(test_pipeline())
