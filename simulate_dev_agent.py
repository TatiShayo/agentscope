# simulate_dev_agent.py

import time
import os
from agentscope.instrumentation import init_tracer, instrument_llm_call, instrument_tool_call

def run_simulation():
    # Initialize OTel Tracer (direct to local exporter)
    print("Initializing tracer...")
    # Jaeger standard OTLP port is 4317 (gRPC) or 4318 (HTTP)
    # We will point it to localhost:4317
    init_tracer(service_name="simulated_developer", endpoint="localhost:4317")
    
    time.sleep(1) # Wait for provider initialization
    
    # 1. LLM call to draft a script
    print("Simulating LLM call to draft script...")
    model_name = "gpt-4o"
    messages = [
        {"role": "system", "content": "You are a developer helper."},
        {"role": "user", "content": "Write a python function to add two numbers."}
    ]
    
    with instrument_llm_call(model=model_name, messages=messages, temperature=0.7, system="openai") as ctx:
        # Simulate LLM request processing delay
        time.sleep(0.5)
        ctx.input_tokens = 45
        ctx.output_tokens = 80
        ctx.response_model = "gpt-4o"
        ctx.completion = "def add(a, b): return a + b"
        print(f"LLM Response: {ctx.completion}")
        
    # 2. Tool call to test/save the function
    print("Simulating tool call to write file...")
    tool_args = {"filename": "calc.py", "content": "def add(a, b): return a + b"}
    tool_result = "Success: File calc.py written."
    instrument_tool_call(tool_name="write_file", args=tool_args, result=tool_result)
    print(f"Tool Result: {tool_result}")
    
    # 3. LLM call to refine/review
    print("Simulating LLM call to review script...")
    messages.append({"role": "assistant", "content": ctx.completion})
    messages.append({"role": "user", "content": "Now write a multiply function."})
    
    with instrument_llm_call(model=model_name, messages=messages, temperature=0.5, system="openai") as ctx2:
        time.sleep(0.3)
        ctx2.input_tokens = 135
        ctx2.output_tokens = 95
        ctx2.response_model = "gpt-4o"
        ctx2.completion = "def multiply(a, b): return a * b"
        print(f"LLM Response: {ctx2.completion}")

    print("Simulation finished. Waiting for trace exporter to flush...")
    time.sleep(3)
    print("Done!")

if __name__ == "__main__":
    run_simulation()
