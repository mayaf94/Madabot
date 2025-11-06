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

    # Add AI analysis
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*🤖 AI Analysis:*\n{analysis[:2800]}"  # Slack has 3000 char limit per block
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
    """Enhanced Slack notifier with Block Kit formatting"""
    print(f"Event: {json.dumps(event)}")

    # Get Slack webhook from Secrets Manager
    secret_name = os.environ['SLACK_WEBHOOK_SECRET']
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret_string = response['SecretString']

    # Parse JSON secret (format: {"saar_slack_webhook": "https://..."})
    secret_data = json.loads(secret_string)
    webhook_url = secret_data['saar_slack_webhook']

    # Parse message
    for record in event.get('Records', []):
        body = json.loads(record['body'])

        severity = body.get('severity', 'UNKNOWN')

        # Build Block Kit message
        blocks = build_slack_blocks(body)

        msg = {
            'attachments': [
                {
                    'color': get_severity_color(severity),
                    'blocks': blocks
                }
            ]
        }

        print(f"Sending Slack message for alert {body.get('alert_id')}")

        resp = http.request(
            'POST',
            webhook_url,
            body=json.dumps(msg),
            headers={'Content-Type': 'application/json'}
        )

        print(f"Slack response status: {resp.status}")

    return {'statusCode': 200}
