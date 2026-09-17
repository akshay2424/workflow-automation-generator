"""
Generate a Mermaid state diagram from a workflow.json.

Mermaid over Graphviz/matplotlib: it renders natively in GitHub READMEs and
most Markdown viewers, so the architecture diagram deliverable needs zero
extra tooling for a reviewer to see it — just open the .md file.
"""
import json



def to_mermaid(workflow_path: str) -> str:
    with open(workflow_path, "r") as f:
        wf = json.load(f)

    lines = ["stateDiagram-v2"]
    lines.append(f"    [*] --> {wf['start_state']}")

    for t in wf["transitions"]:
        label = f" : {t['guard']}" if t["guard"] else ""
        lines.append(f"    {t['from']} --> {t['to']}{label}")

    for end_id in wf["end_states"]:
        lines.append(f"    {end_id} --> [*]")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    print(to_mermaid(sys.argv[1]))
