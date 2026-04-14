"""End-to-end web API test for TPRM AI Web Application."""
import json, time, http.client
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BOUNDARY = "----WebAppTestBoundary123"

def add_field(body, name, value):
    body += f'--{BOUNDARY}\r\n'.encode()
    body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
    body += f'{value}\r\n'.encode()
    return body

def add_file(body, name, filepath):
    fname = filepath.name
    body += f'--{BOUNDARY}\r\n'.encode()
    body += f'Content-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'.encode()
    body += f'Content-Type: application/octet-stream\r\n\r\n'.encode()
    body += filepath.read_bytes()
    body += b'\r\n'
    return body

def main():
    body = b''
    body = add_field(body, 'vendor_name', 'Adobe Cloud Test')
    body = add_field(body, 'use_openai', 'false')

    # Add questionnaire
    q_file = ROOT / 'inputs' / 'questionnaires' / 'Adobe_Cloud - 2023 SIG Lite - 1.0.pdf'
    body = add_file(body, 'questionnaires', q_file)

    # Add 2 artifacts
    a_dir = ROOT / 'inputs' / 'artifacts'
    a_files = sorted(a_dir.iterdir())[:2]
    for f in a_files:
        body = add_file(body, 'artifacts', f)

    # Add policy
    p_file = ROOT / 'inputs' / 'policies' / '(TCL-IS-030) IT Supplier Third-Party Risk Management (TPRM) Policy.pdf'
    body = add_file(body, 'policies', p_file)

    # Add clauses
    c_file = ROOT / 'inputs' / 'contract_clauses' / 'Info-sec clauses for Adobe Cloud.docx'
    body = add_file(body, 'contract_clauses', c_file)

    body += f'--{BOUNDARY}--\r\n'.encode()
    print(f"Request body: {len(body)} bytes")

    # 1. Create assessment
    conn = http.client.HTTPConnection('127.0.0.1', 8085)
    headers = {'Content-Type': f'multipart/form-data; boundary={BOUNDARY}'}
    conn.request('POST', '/api/assessments', body=body, headers=headers)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    print(f"CREATE: {resp.status}")
    print(f"  id: {data.get('id')}")
    print(f"  vendor: {data.get('vendor_name')}")
    conn.close()

    assessment_id = data.get('id')
    if not assessment_id:
        print("FAILED to create assessment")
        return

    # 2. Trigger pipeline
    conn2 = http.client.HTTPConnection('127.0.0.1', 8085)
    conn2.request('POST', f'/api/assessments/{assessment_id}/run')
    resp2 = conn2.getresponse()
    run_data = json.loads(resp2.read().decode())
    print(f"RUN: {resp2.status} - {run_data.get('message', '')}")
    conn2.close()

    # 3. Poll status
    for i in range(120):
        time.sleep(3)
        conn3 = http.client.HTTPConnection('127.0.0.1', 8085)
        conn3.request('GET', f'/api/assessments/{assessment_id}/status')
        resp3 = conn3.getresponse()
        status_data = json.loads(resp3.read().decode())
        conn3.close()
        status = status_data.get('status')
        step = status_data.get('current_step', '?')
        total = status_data.get('total_steps', '?')
        msg = status_data.get('step_message', '')
        print(f"  Poll {i+1}: {status} - step {step}/{total} - {msg}")
        if status in ('completed', 'failed'):
            if status == 'failed':
                print(f"ERROR: {status_data.get('error')}")
            break
    else:
        print("TIMEOUT waiting for pipeline")

    # 4. Check results
    if status == 'completed':
        conn4 = http.client.HTTPConnection('127.0.0.1', 8085)
        conn4.request('GET', f'/api/assessments/{assessment_id}/results')
        resp4 = conn4.getresponse()
        results = json.loads(resp4.read().decode())
        conn4.close()
        print(f"\nRESULTS:")
        print(f"  Risk Rating: {results.get('risk_rating', {}).get('overall', 'N/A')}")
        print(f"  Gaps: {len(results.get('gaps', []))}")
        print(f"  Risks: {len(results.get('risks', []))}")
        print(f"  Recommendations: {len(results.get('recommendations', []))}")
        print(f"  Compliance: {len(results.get('compliance_mapping', []))}")

    # 5. Check detail page
    conn5 = http.client.HTTPConnection('127.0.0.1', 8085)
    conn5.request('GET', f'/assessments/{assessment_id}')
    resp5 = conn5.getresponse()
    detail_html = resp5.read()
    conn5.close()
    print(f"\nDetail page: {resp5.status} ({len(detail_html)} bytes)")

    print("\n=== TEST COMPLETE ===")

if __name__ == '__main__':
    main()
