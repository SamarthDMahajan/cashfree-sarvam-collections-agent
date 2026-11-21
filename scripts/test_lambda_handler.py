"""
Direct unit test for lambda_handler.py.
Verifies:
1. Raw JSON event invocation
2. HTTP API Gateway proxy event with stringified body
3. Return format: {statusCode: 200, headers: {...}, body: json_string} (no binary images!)
"""
import os
import sys
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lambda_handler import lambda_handler

def test_lambda():
    print("=" * 60)
    print("TESTING AWS LAMBDA HANDLER INTERFACE")
    print("=" * 60)

    # 1. Test Health / Ping
    res1 = lambda_handler({"action": "health"})
    assert res1["statusCode"] == 200
    body1 = json.loads(res1["body"])
    print(f"[TEST 1] Raw JSON Health: {body1['service']} -> {body1['status']}")

    # 2. Test HTTP Gateway Proxy Event with Cashfree Webhook
    with open("scripts/relay_sample_payload.json", "r") as f:
        payload_data = f.read()

    proxy_event = {
        "httpMethod": "POST",
        "path": "/samarthdmahajan-collections-agent/",
        "headers": {"Content-Type": "application/json"},
        "body": payload_data,
        "isBase64Encoded": False
    }

    res2 = lambda_handler(proxy_event)
    assert res2["statusCode"] == 200
    body2 = json.loads(res2["body"])
    print(f"[TEST 2] HTTP Proxy Event: Status={body2['status']}, Link={body2['link_id']}, Action={body2['queue_action']}")
    assert body2["status"] == "SUCCESS"
    assert body2["queue_action"] == "DROP_FROM_CALL_QUEUE"

    # 3. Test Compliance Check via Lambda
    comp_event = {
        "action": "compliance_check",
        "borrower": {
            "loan_id": "LN-TEST-001",
            "notes": "admitted in hospital surgery yesterday",
            "preferred_language": "hi-IN"
        }
    }
    res3 = lambda_handler(comp_event)
    assert res3["statusCode"] == 200
    body3 = json.loads(res3["body"])
    comp = body3["compliance"]
    print(f"[TEST 3] Lambda Compliance Check: Allowed={comp['allowed']}, Stage={comp['stage']}")
    assert not comp["allowed"] and comp["stage"] == "COMPASSIONATE_HOLD"

    print("\n" + "=" * 60)
    print("ALL LAMBDA HANDLER CHECKS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    test_lambda()

