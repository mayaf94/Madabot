import json
import os
import boto3
import urllib3
from urllib.parse import parse_qs
from decimal import Decimal
import hmac
import hashlib
import time

http = urllib3.PoolManager()
sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Helper to convert DynamoDB Decimal to JSON-serializable types
def decimal_to_native(obj):
    """Convert Decimal types from DynamoDB to native Python types"""
    if isinstance(obj, list):
        return [decimal_to_native(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: decimal_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj

def verify_slack_request(event):
    """Verify that the request came from Slack"""
    try:
        # Get Slack signing secret from environment
        signing_secret_name = os.environ.get('SLACK_SIGNING_SECRET')
        if not signing_secret_name:
            print("⚠️ Slack signing secret not configured")
            return True  # Skip verification if not configured

        response = secrets_client.get_secret_value(SecretId=signing_secret_name)
        try:
            secret_data = json.loads(response['SecretString'])
            signing_secret = secret_data.get('signing_secret')
        except json.JSONDecodeError:
            signing_secret = response['SecretString']

        # Get Slack signature and timestamp from headers
        headers = {k.lower(): v for k, v in event.get('headers', {}).items()}
        slack_signature = headers.get('x-slack-signature')
        slack_timestamp = headers.get('x-slack-request-timestamp')

        if not slack_signature or not slack_timestamp:
            print("❌ Missing Slack signature or timestamp")
            return False

        # Check timestamp to prevent replay attacks (within 5 minutes)
        if abs(time.time() - int(slack_timestamp)) > 60 * 5:
            print("❌ Request timestamp too old")
            return False

        # Verify signature
        body = event.get('body', '')
        sig_basestring = f"v0:{slack_timestamp}:{body}"
        my_signature = 'v0=' + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(my_signature, slack_signature):
            print("❌ Invalid Slack signature")
            return False

        return True

    except Exception as e:
        print(f"⚠️ Error verifying Slack request: {e}")
        return True  # Allow through if verification fails

def get_alert_from_dynamodb(alert_id):
    """Retrieve alert details from DynamoDB"""
    try:
        table_name = os.environ.get('ALERTS_TABLE')
        table = dynamodb.Table(table_name)

        response = table.get_item(Key={'alert_id': alert_id})
        return response.get('Item')

    except Exception as e:
        print(f"Error retrieving alert from DynamoDB: {e}")
        return None

def send_to_jira_queue(alert_data):
    """Send alert to Jira processing queue"""
    try:
        jira_queue_url = os.environ.get('JIRA_QUEUE_URL')
        if not jira_queue_url:
            print("❌ Jira queue URL not configured")
            return False

        # Convert Decimal types to native Python types for JSON serialization
        clean_data = decimal_to_native(alert_data)

        sqs.send_message(
            QueueUrl=jira_queue_url,
            MessageBody=json.dumps(clean_data),
            MessageGroupId='jira-tickets'
        )

        print(f"✅ Sent alert to Jira queue for processing")
        return True

    except Exception as e:
        print(f"❌ Error sending to Jira queue: {e}")
        return False

def update_slack_message(response_url, message):
    """Update the original Slack message"""
    try:
        response = http.request(
            'POST',
            response_url,
            body=json.dumps(message),
            headers={'Content-Type': 'application/json'}
        )

        if response.status == 200:
            print("✅ Updated Slack message")
            return True
        else:
            print(f"❌ Failed to update Slack message: {response.status}")
            return False

    except Exception as e:
        print(f"❌ Error updating Slack message: {e}")
        return False

def handle_create_jira(payload):
    """Handle 'Create Jira' button click"""
    alert_id = payload['actions'][0]['value']
    user = payload['user']['name']
    response_url = payload['response_url']

    print(f"Creating Jira ticket for alert {alert_id} (requested by {user})")

    # Get alert details from DynamoDB
    alert_data = get_alert_from_dynamodb(alert_id)

    if not alert_data:
        print(f"❌ Alert {alert_id} not found in database")
        # Update Slack message
        update_slack_message(response_url, {
            "text": f"❌ Error: Alert not found in database. Please try again or contact support."
        })
        return

    # Send to Jira processing queue
    success = send_to_jira_queue(alert_data)

    if success:
        # Update Slack message to show Jira ticket is being created
        update_slack_message(response_url, {
            "text": f"🎫 Jira ticket is being created by {user}...",
            "replace_original": False
        })
    else:
        update_slack_message(response_url, {
            "text": f"❌ Failed to create Jira ticket. Please try again or contact support."
        })

def handle_acknowledge(payload):
    """Handle 'Acknowledge' button click"""
    alert_id = payload['actions'][0]['value']
    user = payload['user']['name']
    response_url = payload['response_url']

    print(f"Alert {alert_id} acknowledged by {user}")

    # Update Slack message
    update_slack_message(response_url, {
        "text": f"✅ Alert acknowledged by {user}",
        "replace_original": False
    })

    # TODO: Update DynamoDB to mark alert as acknowledged
    # table.update_item(
    #     Key={'alert_id': alert_id},
    #     UpdateExpression='SET acknowledged = :ack, acknowledged_by = :user, acknowledged_at = :time',
    #     ExpressionAttributeValues={
    #         ':ack': True,
    #         ':user': user,
    #         ':time': datetime.utcnow().isoformat()
    #     }
    # )

def lambda_handler(event, context):
    """Slack Interactions Handler - Handles button clicks and other Slack interactions"""
    print(f"Received event: {json.dumps(event)}")

    # Verify request is from Slack
    if not verify_slack_request(event):
        return {
            'statusCode': 403,
            'body': json.dumps({'error': 'Invalid request signature'})
        }

    # Parse the payload
    body = event.get('body', '')
    if event.get('isBase64Encoded'):
        import base64
        body = base64.b64decode(body).decode('utf-8')

    # Slack sends the payload as URL-encoded form data
    parsed_body = parse_qs(body)
    payload_json = parsed_body.get('payload', ['{}'])[0]
    payload = json.loads(payload_json)

    print(f"Payload type: {payload.get('type')}")
    print(f"Action: {payload.get('actions', [{}])[0].get('action_id') if payload.get('actions') else 'None'}")

    # Handle different interaction types
    interaction_type = payload.get('type')

    if interaction_type == 'block_actions':
        action = payload['actions'][0]
        action_id = action['action_id']

        if action_id == 'create_jira':
            handle_create_jira(payload)
        elif action_id == 'acknowledge_alert':
            handle_acknowledge(payload)
        else:
            print(f"⚠️ Unknown action: {action_id}")

        # Return 200 immediately to Slack
        return {
            'statusCode': 200,
            'body': ''
        }

    # Handle URL verification (Slack sends this when you configure the endpoint)
    elif interaction_type == 'url_verification':
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'challenge': payload.get('challenge')})
        }

    else:
        print(f"⚠️ Unknown interaction type: {interaction_type}")
        return {
            'statusCode': 200,
            'body': ''
        }
