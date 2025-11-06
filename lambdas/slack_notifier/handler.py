import json
import os
import boto3
import urllib3
from datetime import datetime

http = urllib3.PoolManager()
secrets_client = boto3.client('secretsmanager')

def get_severity_color(severity):
    """Map severity to Slack color"""
    severity_colors = {
        'CRITICAL': '#FF0000',  # Red
        'HIGH': '#FF6B00',      # Orange
        'MEDIUM': '#FFD500',    # Yellow
        'LOW': '#36A64F'        # Green
    }
    return severity_colors.get(severity, '#808080')

def get_severity_emoji(severity):
    """Map severity to emoji"""
    severity_emojis = {
        'CRITICAL': '🔴',
        'HIGH': '🟠',
        'MEDIUM': '🟡',
        'LOW': '🟢'
    }
    return severity_emojis.get(severity, '⚪')

def extract_analysis_summary(analysis):
    """Extract a concise summary from the full AI analysis"""
    # Try to extract key sections from the analysis
    lines = analysis.split('\n')
    summary_parts = []

    # Look for key sections
    in_severity = False
    in_root_cause = False
    in_impact = False
    in_actions = False

    severity_lines = []
    root_cause_lines = []
    impact_lines = []
    action_lines = []

    for line in lines:
        line_lower = line.lower().strip()

        # Detect section headers
        if 'severity' in line_lower and ('assessment' in line_lower or ':' in line):
            in_severity = True
            in_root_cause = False
            in_impact = False
            in_actions = False
            continue
        elif 'root cause' in line_lower or 'most likely' in line_lower:
            in_severity = False
            in_root_cause = True
            in_impact = False
            in_actions = False
            continue
        elif 'impact' in line_lower and ('assessment' in line_lower or ':' in line):
            in_severity = False
            in_root_cause = False
            in_impact = True
            in_actions = False
            continue
        elif 'recommend' in line_lower or 'action' in line_lower or 'remediation' in line_lower:
            in_severity = False
            in_root_cause = False
            in_impact = False
            in_actions = True
            continue
        elif line.startswith('##') or line.startswith('---'):
            # Section break
            in_severity = False
            in_root_cause = False
            in_impact = False
            in_actions = False
            continue

        # Collect relevant lines
        if in_root_cause and line.strip() and not line.startswith('#'):
            root_cause_lines.append(line.strip())
            if len(root_cause_lines) >= 3:
                in_root_cause = False
        elif in_impact and line.strip() and not line.startswith('#'):
            impact_lines.append(line.strip())
            if len(impact_lines) >= 2:
                in_impact = False
        elif in_actions and line.strip() and not line.startswith('#'):
            if line.strip().startswith(('•', '-', '*', '1', '2', '3')):
                action_lines.append(line.strip())
                if len(action_lines) >= 3:
                    in_actions = False

    # Build concise summary
    if root_cause_lines:
        # Take first substantive sentence
        for line in root_cause_lines[:3]:
            if len(line) > 30 and not line.startswith('**'):
                summary_parts.append(f"*Root Cause:* {line[:200]}")
                break

    if impact_lines:
        for line in impact_lines[:2]:
            if len(line) > 20 and not line.startswith('**'):
                summary_parts.append(f"*Impact:* {line[:150]}")
                break

    if action_lines:
        actions = []
        for line in action_lines[:3]:
            cleaned = line.lstrip('•-*123456789. ')
            if len(cleaned) > 10:
                actions.append(f"• {cleaned[:100]}")
        if actions:
            summary_parts.append(f"*Actions:*\n" + '\n'.join(actions))

    if summary_parts:
        return '\n\n'.join(summary_parts)
    else:
        # Fallback: take first 500 chars
        return analysis[:500] + "..."

def build_slack_blocks(body):
    """Build Slack Block Kit message"""
    severity = body.get('severity', 'UNKNOWN')
    alert_message = body.get('alert', 'No alert message')
    analysis = body.get('analysis', 'No analysis available')
    alert_id = body.get('alert_id', 'unknown')
    log_group = body.get('log_group', '')
    log_stream = body.get('log_stream', '')
    model = body.get('model', 'unknown')

    # Get infrastructure context
    infra_context = body.get('infrastructure_context', {})
    infra_type = infra_context.get('type', 'unknown')
    resource_id = infra_context.get('resource_id', '')
    pod_name = infra_context.get('pod_name', '')
    task_id = infra_context.get('task_id', '')

    # Build infrastructure context text
    infra_text = f"*Infrastructure:* {infra_type}"
    if resource_id:
        infra_text += f" | Resource: `{resource_id}`"
    if pod_name:
        infra_text += f" | Pod: `{pod_name}`"
    if task_id:
        infra_text += f" | Task: `{task_id[:12]}...`"

    # Timestamp
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{get_severity_emoji(severity)} Alert: {severity}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Alert Message:*\n```{alert_message[:500]}```"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Severity:*\n{get_severity_emoji(severity)} {severity}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Alert ID:*\n`{alert_id[:16]}...`"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Timestamp:*\n{timestamp}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*AI Model:*\n{model}"
                }
            ]
        }
    ]

    # Add infrastructure context if available
    if infra_type != 'unknown':
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": infra_text
            }
        })

    # Add log location
    if log_group:
        log_text = f"*Log Location:*\n• Group: `{log_group}`"
        if log_stream:
            log_text += f"\n• Stream: `{log_stream[:50]}...`"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": log_text
            }
        })

    # Add divider
    blocks.append({"type": "divider"})

    # Add AI analysis summary
    analysis_summary = extract_analysis_summary(analysis)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*🤖 AI Analysis Summary:*\n{analysis_summary}\n\n_💡 Full analysis available in Jira ticket_"
        }
    })

    # Add action buttons
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "✅ Acknowledge",
                    "emoji": True
                },
                "style": "primary",
                "value": alert_id,
                "action_id": "acknowledge_alert"
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "🎫 Create Jira",
                    "emoji": True
                },
                "value": alert_id,
                "action_id": "create_jira"
            }
        ]
    })

    # Add CloudWatch Logs link if available
    if log_group and log_stream:
        region = os.environ.get('AWS_REGION', 'us-east-1')
        log_group_encoded = log_group.replace('/', '$252F')
        log_stream_encoded = log_stream.replace('/', '$252F')
        cloudwatch_url = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group_encoded}/log-events/{log_stream_encoded}"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{cloudwatch_url}|📊 View in CloudWatch Logs>"
            }
        })

    return blocks

def lambda_handler(event, context):
    """Enhanced Slack notifier with Block Kit formatting using Slack Web API"""
    print(f"Event: {json.dumps(event)}")

    # Get Slack bot token from Secrets Manager
    secret_name = os.environ.get('SLACK_BOT_TOKEN_SECRET', 'slack-bot-token')
    response = secrets_client.get_secret_value(SecretId=secret_name)

    # Bot token can be stored as plain text or JSON
    try:
        secret_data = json.loads(response['SecretString'])
        bot_token = secret_data.get('bot_token', secret_data.get('slack_bot_token'))
    except json.JSONDecodeError:
        # If it's plain text, use it directly
        bot_token = response['SecretString']

    # Get Slack channel from environment variable
    slack_channel = os.environ.get('SLACK_CHANNEL', '#alerts')

    # Parse message
    for record in event.get('Records', []):
        body = json.loads(record['body'])

        severity = body.get('severity', 'UNKNOWN')

        # Build Block Kit message
        blocks = build_slack_blocks(body)

        # Slack Web API message format
        msg = {
            'channel': slack_channel,
            'attachments': [
                {
                    'color': get_severity_color(severity),
                    'blocks': blocks
                }
            ]
        }

        print(f"Sending Slack message for alert {body.get('alert_id')} to {slack_channel}")

        # Use Slack Web API chat.postMessage
        resp = http.request(
            'POST',
            'https://slack.com/api/chat.postMessage',
            body=json.dumps(msg),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {bot_token}'
            }
        )

        response_data = json.loads(resp.data.decode('utf-8'))
        print(f"Slack API response: {json.dumps(response_data)}")

        if not response_data.get('ok'):
            error = response_data.get('error', 'Unknown error')
            print(f"❌ Slack API error: {error}")
            raise Exception(f"Slack API error: {error}")
        else:
            print(f"✅ Message sent successfully to {slack_channel}")

    return {'statusCode': 200}
