# demo_approval_gate.py

import os
from agentscope.ledger import update_task_trace, resolve_trace_link

def run_demo():
    ledger_path = "TASK_LEDGER.json"
    phase_num = 2
    task_id = "parallel_dispatch_simulation"
    # Using the trace ID generated in Phase 2
    trace_id = "04b521bdf3a9757beb39b2b03bb6770b"
    
    print(f"Updating ledger '{ledger_path}' task '{task_id}' with trace_id '{trace_id}'...")
    success = update_task_trace(ledger_path, phase_num, task_id, trace_id)
    
    if success:
        print("Successfully updated task entry!")
        print("Resolving trace link from task entry...")
        link = resolve_trace_link(ledger_path, phase_num, task_id)
        print(f"\nResolved Direct Jaeger Link: {link}\n")
    else:
        print("Failed to find or update task entry in ledger.")

if __name__ == "__main__":
    run_demo()
