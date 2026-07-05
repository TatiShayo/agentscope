# simulate_hierarchy.py

import time
import threading
from opentelemetry import trace
from agentscope.instrumentation import init_tracer, instrument_llm_call, instrument_tool_call, dispatch_subagent

def run_developer_task(dev_span):
    print("Developer: Starting task...")
    # LLM call inside Developer subagent
    with instrument_llm_call(model="gpt-4", messages=[{"role": "user", "content": "implement code"}], system="openai") as ctx:
        time.sleep(0.4)
        ctx.input_tokens = 100
        ctx.output_tokens = 150
        ctx.response_model = "gpt-4"
        ctx.completion = "def target_func(): pass"
    
    # Tool call inside Developer subagent
    instrument_tool_call(tool_name="save_code", args={"code": "def target_func(): pass"}, result="saved")
    time.sleep(0.2)
    print("Developer: Done.")

def run_security_task(review_span):
    print("Security: Starting audit...")
    # Wrap in dispatch_subagent with the shared review parent span
    with dispatch_subagent(review_span, "Security", "Audit code diff for safety") as sec_span:
        with instrument_llm_call(model="claude-3-5-sonnet", messages=[{"role": "user", "content": "audit code"}], system="anthropic") as ctx:
            time.sleep(0.6)
            ctx.input_tokens = 200
            ctx.output_tokens = 120
            ctx.response_model = "claude-3-5-sonnet"
            ctx.completion = "Audit result: Safe"
    print("Security: Done.")

def run_qa_task(review_span):
    print("QA: Starting test suite execution...")
    # Wrap in dispatch_subagent with the shared review parent span
    with dispatch_subagent(review_span, "QA", "Execute unit and integration tests") as qa_span:
        # Tool call representing running test commands
        instrument_tool_call(tool_name="pytest", args={"test_path": "tests/"}, result="3 passes, 0 failures")
        
        with instrument_llm_call(model="gpt-3.5-turbo", messages=[{"role": "user", "content": "analyze test coverage"}], system="openai") as ctx:
            time.sleep(0.5)
            ctx.input_tokens = 80
            ctx.output_tokens = 50
            ctx.response_model = "gpt-3.5-turbo"
            ctx.completion = "100% coverage"
    print("QA: Done.")

def main():
    # Initialize OTel Tracer (sending directly to local Jaeger)
    tracer = init_tracer(service_name="hierarchical_agents", endpoint="localhost:4317")
    
    print("Lead Agent: Initiating orchestration cycle...")
    
    # Root span: Orchestration Cycle
    with tracer.start_as_current_span("Lead Orchestration") as lead_span:
        lead_span.set_attribute("orchestration.task", "Build and verify feature X")
        time.sleep(0.2)
        
        # 1. Dispatch Developer
        print("Lead Agent: Dispatching Developer...")
        with dispatch_subagent(lead_span, "Developer", "Write implementation") as dev_span:
            run_developer_task(dev_span)
            
        time.sleep(0.2)
        
        # 2. Parallel dispatch of Security and QA
        print("Lead Agent: Developer finished. Starting Review Cycle (parallel Security & QA)...")
        
        # Create a shared "Review Cycle" span under lead_span
        context = trace.set_span_in_context(lead_span)
        with tracer.start_as_current_span("Review Cycle", context=context) as review_span:
            
            # Create threads for parallel execution
            sec_thread = threading.Thread(target=run_security_task, args=(review_span,))
            qa_thread = threading.Thread(target=run_qa_task, args=(review_span,))
            
            # Start threads in parallel
            sec_thread.start()
            qa_thread.start()
            
            # Wait for both to complete
            sec_thread.join()
            qa_thread.join()
            
        print("Lead Agent: Review Cycle complete. Finalizing orchestration...")
        time.sleep(0.1)

    print("Orchestration complete. Flushing traces...")
    time.sleep(3)
    print("Done!")

if __name__ == "__main__":
    main()
