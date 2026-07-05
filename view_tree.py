import urllib.request
import json
import sys

def print_trace_tree(trace_id):
    url = f"http://localhost:16686/api/traces/{trace_id}"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching trace: {e}")
        return

    if not data.get("data"):
        print("No data found for trace.")
        return

    trace_data = data["data"][0]
    spans = trace_data["spans"]
    
    # Map spanID to span object
    span_map = {s["spanID"]: s for s in spans}
    
    # Reconstruct parent-child relations
    children = {}
    roots = []
    
    for s in spans:
        parent_id = None
        for ref in s.get("references", []):
            if ref["refType"] == "CHILD_OF":
                parent_id = ref["spanID"]
                break
        
        if parent_id and parent_id in span_map:
            children.setdefault(parent_id, []).append(s["spanID"])
        else:
            roots.append(s["spanID"])

    def print_node(span_id, indent=""):
        span = span_map[span_id]
        op_name = span["operationName"]
        # Extract role or system if present in tags
        tags = {t["key"]: t["value"] for t in span.get("tags", [])}
        details = []
        if "agent.role" in tags:
            details.append(f"role={tags['agent.role']}")
        if "gen_ai.request.model" in tags:
            details.append(f"model={tags['gen_ai.request.model']}")
        if "tool.name" in tags:
            details.append(f"tool={tags['tool.name']}")
            
        details_str = f" [{', '.join(details)}]" if details else ""
        print(f"{indent}- {op_name}{details_str}")
        
        # Sort children by startTime to display in execution order
        child_spans = children.get(span_id, [])
        child_spans.sort(key=lambda cid: span_map[cid]["startTime"])
        for child_id in child_spans:
            print_node(child_id, indent + "  ")

    for root in roots:
        print_node(root)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python view_tree.py <trace_id>")
    else:
        print_trace_tree(sys.argv[1])
