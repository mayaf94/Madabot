import json
import os
import boto3
import urllib3
from context_gatherer import ContextGatherer

http = urllib3.PoolManager()
ssm = boto3.client('ssm')
sqs = boto3.client('sqs')

# Initialize context gatherer
context_gatherer = ContextGatherer()

def lambda_handler(event, context):
    """
    Enhanced analyzer Lambda with infrastructure context gathering
    """
    print(f"Received event: {json.dumps(event)}")

    # Get API key from SSM
    api_key_param = os.environ.get('GOOGLE_API_KEY_PARAM')
    response = ssm.get_parameter(Name=api_key_param, WithDecryption=True)
    api_key = response['Parameter']['Value']

    # Get distribution queue URL
    distribution_queue_url = os.environ.get('DISTRIBUTION_QUEUE_URL')

    # Parse alert from SQS event
    for record in event.get('Records', []):
        body = json.loads(record['body'])
        alert_message = body.get('message', 'Unknown error')

        print(f"Processing alert: {body.get('alert_id')}")

        # Gather infrastructure context
        print("Gathering infrastructure context...")
        try:
            infra_context = context_gatherer.gather_all_context(body)
            context_text = context_gatherer.format_context_for_prompt(infra_context)
            print(f"Context gathered successfully. Length: {len(context_text)} chars")
        except Exception as e:
            print(f"Error gathering context: {e}")
            context_text = "Context gathering failed - analyzing with limited information"
            infra_context = {}

        # Create enhanced prompt with context
        prompt = f"""You are an expert SRE analyzing a production alert. Analyze this alert with the provided infrastructure context and provide actionable insights.

## Alert
{alert_message}

{context_text}

## Analysis Required
Provide a structured analysis with:

1. **Severity Assessment** (CRITICAL/HIGH/MEDIUM/LOW)
   - Validate or adjust the severity based on context
   - Consider impact on users and systems

2. **Root Cause Analysis**
   - What is the most likely root cause?
   - Use infrastructure context to identify specific issues
   - Reference specific resources (Pod names, Task IDs, etc.)

3. **Impact Assessment**
   - Which systems/users are affected?
   - Is this a partial or total outage?

4. **Recommended Actions** (prioritized list)
   - Immediate mitigation steps
   - Investigation steps
   - Long-term fixes

5. **Monitoring Recommendations**
   - What metrics should be watched?
   - What would indicate the issue is resolved?

6. **Confidence Score** (0.0-1.0)
   - How confident are you in this analysis?

Format the response clearly with headers and bullet points."""

        # Call Gemini REST API
        url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}'

        payload = {
            'contents': [{
                'parts': [{'text': prompt}]
            }]
        }

        resp = http.request(
            'POST',
            url,
            body=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )

        result = json.loads(resp.data.decode('utf-8'))
        print(f"Gemini API Response: {json.dumps(result)}")

        # Check for errors
        if 'error' in result:
            error_msg = result['error'].get('message', 'Unknown error')
            print(f"Gemini API Error: {error_msg}")
            analysis = f"Error calling Gemini: {error_msg}"
        elif 'candidates' in result:
            analysis = result['candidates'][0]['content']['parts'][0]['text']
        else:
            analysis = "No analysis returned from Gemini"

        print(f"Analysis: {analysis[:500]}...")  # Log first 500 chars

        # Send analysis to distribution queue with enhanced data
        distribution_message = {
            'alert_id': body.get('alert_id'),
            'alert': alert_message,
            'analysis': analysis,
            'severity': body.get('severity', 'UNKNOWN'),
            'source': body.get('source', 'unknown'),
            'model': 'gemini-2.5-flash',
            'log_group': body.get('log_group', ''),
            'log_stream': body.get('log_stream', ''),
            'infrastructure_context': {
                'type': infra_context.get('log_context', {}).get('infrastructure_type', 'unknown'),
                'resource_id': infra_context.get('log_context', {}).get('resource_id', ''),
                'pod_name': infra_context.get('log_context', {}).get('pod_name', ''),
                'task_id': infra_context.get('log_context', {}).get('task_id', ''),
            }
        }

        sqs.send_message(
            QueueUrl=distribution_queue_url,
            MessageBody=json.dumps(distribution_message),
            MessageGroupId='analysis'
        )

        print(f"Sent enhanced analysis to distribution queue: {distribution_queue_url}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'alert': alert_message,
                'analysis': analysis,
                'model': 'gemini-2.5-flash',
                'context_gathered': len(context_text) > 0
            })
        }

    return {'statusCode': 200, 'body': 'No records processed'}
