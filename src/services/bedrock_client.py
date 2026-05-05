import hashlib
import json
import os

import boto3

MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
_client = None


def _bedrock():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=os.getenv("BEDROCK_REGION", "us-east-1"))
    return _client


def synthesize(vendor_name: str, evidence: dict) -> tuple[str, str, str]:
    prompt = f"""You are a compliance analyst. Synthesize the following due diligence results for vendor "{vendor_name}" into a structured risk assessment.

Evidence:
{json.dumps(evidence, indent=2)}

Return a JSON object with:
- risk_level: "low" | "medium" | "high" | "critical"
- recommendation: "APPROVE" | "ENHANCED_DILIGENCE" | "REJECT"
- summary: 2-3 sentence explanation
- key_findings: list of 3-5 bullet points

Return only valid JSON."""

    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

    response = _bedrock().converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )

    output = response["output"]["message"]["content"][0]["text"]
    # Strip markdown code fences if present
    if output.startswith("```"):
        output = output.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return output, prompt_hash, MODEL_ID
