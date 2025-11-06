import json
import os
import boto3
import urllib3
import base64
from datetime import datetime

http = urllib3.PoolManager()
ssm = boto3.client('ssm')
secrets_client = boto3.client('secretsmanager')

def map_severity_to_jira_priority(severity):
    """Map alert severity to Jira priority"""
    severity_map = {
        'CRITICAL': 'Highest',
        'HIGH': 'High',
        'MEDIUM': 'Medium',
        'LOW': 'Low'
    }
    return severity_map.get(severity, 'Medium')

def format_jira_description(alert, analysis):
    """Format incident description for Jira (Jira Wiki Markup)"""
    parts = [
        "h2. Incident Summary",
        f"{analysis}",
        "",
        "h3. Alert Details",
        f"* *Source:* {alert.get('source', 'Unknown')}",
        f"* *Severity:* {alert.get('severity', 'Unknown')}",
        f"* *Timestamp:* {alert.get('timestamp', datetime.utcnow().isoformat())}",
        f"* *Alert ID:* {alert.get('alert_id', 'Unknown')}",
        ""
    ]

    if alert.get('log_group'):
        parts.extend([
            "h3. Log Information",
            f"* *Log Group:* {{noformat}}{alert['log_group']}{{noformat}}",
        ])
        if alert.get('log_stream'):
            parts.append(f"* *Log Stream:* {{noformat}}{alert['log_stream']}{{noformat}}")
        parts.append("")

    infra_context = alert.get('infrastructure_context', {})
    if infra_context.get('type') and infra_context['type'] != 'unknown':
        parts.extend([
            "h3. Infrastructure Context",
            f"* *Type:* {infra_context['type']}",
        ])
        if infra_context.get('resource_id'):
            parts.append(f"* *Resource ID:* {infra_context['resource_id']}")
        if infra_context.get('pod_name'):
            parts.append(f"* *Pod:* {infra_context['pod_name']}")
        if infra_context.get('task_id'):
            parts.append(f"* *Task ID:* {infra_context['task_id']}")
        parts.append("")

    parts.extend([
        "h3. Alert Message",
        "{noformat}",
        alert.get('alert', alert.get('message', 'No message available')),
        "{noformat}",
        "",
        "h3. AI Analysis",
        analysis[:3000] if len(analysis) > 3000 else analysis,
        "",
        "---",
        "_This ticket was created automatically by MCP First Responder_"
    ])

    return "\n".join(parts)

def create_jira_ticket(alert, analysis, jira_config):
    """Create a Jira ticket for the alert"""
    try:
        # Build Jira issue
        issue_data = {
            "fields": {
                "project": {"key": jira_config['project_key']},
                "summary": f"[{alert.get('severity', 'ALERT')}] {alert.get('alert', alert.get('message', 'Alert'))[:200]}",
                "description": format_jira_description(alert, analysis),
                "issuetype": {"name": jira_config.get('issue_type', 'Task')},
                "priority": {"name": map_severity_to_jira_priority(alert.get('severity', 'MEDIUM'))},
                "labels": [
                    "automated-alert",
                    f"severity-{alert.get('severity', 'medium').lower()}",
                    alert.get('source', 'unknown'),
                    "mcp-first-responder"
                ]
            }
        }

        print(f"Creating Jira ticket in project {jira_config['project_key']}")

        # Prepare Basic Auth header (Jira requires email:api_token in base64)
        # The api_token should already be in format "email:token"
        auth_bytes = jira_config['api_token'].encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')

        # Make API call to create issue
        response = http.request(
            'POST',
            f"{jira_config['url']}/rest/api/2/issue",
            body=json.dumps(issue_data),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Basic {auth_b64}'
            }
        )

        response_data = json.loads(response.data.decode('utf-8'))

        if response.status in [200, 201]:
            ticket_key = response_data.get('key')
            ticket_url = f"{jira_config['url']}/browse/{ticket_key}"
            print(f"✅ Jira ticket created: {ticket_key} - {ticket_url}")
            return {
                'success': True,
                'ticket_key': ticket_key,
                'ticket_url': ticket_url
            }
        else:
            print(f"❌ Failed to create Jira ticket. Status: {response.status}")
            print(f"Response: {response_data}")
            return {
                'success': False,
                'error': response_data.get('errors', response_data)
            }

    except Exception as e:
        print(f"❌ Error creating Jira ticket: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }

def lambda_handler(event, context):
    """Jira Notifier - Creates Jira tickets for alerts"""
    print(f"Received event: {json.dumps(event)}")

    # Get Jira configuration from environment
    jira_url = os.environ.get('JIRA_URL')
    jira_project_key = os.environ.get('JIRA_PROJECT_KEY')
    jira_issue_type = os.environ.get('JIRA_ISSUE_TYPE', 'Task')
    jira_api_token_param = os.environ.get('JIRA_API_TOKEN_PARAM')

    if not all([jira_url, jira_project_key, jira_api_token_param]):
        print("❌ Jira configuration incomplete. Skipping Jira notification.")
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Jira not configured'})
        }

    # Get Jira API token from SSM Parameter Store
    try:
        response = ssm.get_parameter(Name=jira_api_token_param, WithDecryption=True)
        jira_api_token = response['Parameter']['Value']
    except Exception as e:
        print(f"❌ Failed to retrieve Jira API token from SSM: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Failed to retrieve Jira credentials'})
        }

    jira_config = {
        'url': jira_url,
        'api_token': jira_api_token,
        'project_key': jira_project_key,
        'issue_type': jira_issue_type
    }

    # Process each message from SQS
    for record in event.get('Records', []):
        body = json.loads(record['body'])

        alert = body.get('alert', body.get('message', 'No alert message'))
        analysis = body.get('analysis', 'No analysis available')

        # Create Jira ticket
        result = create_jira_ticket(body, analysis, jira_config)

        if result['success']:
            print(f"Jira ticket created: {result['ticket_url']}")
        else:
            print(f"Failed to create Jira ticket: {result.get('error')}")

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Jira notification processed'})
    }
