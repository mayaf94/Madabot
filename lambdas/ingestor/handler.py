import json
import os
import boto3
import gzip
import base64
from datetime import datetime

sqs = boto3.client('sqs')

def parse_cloudwatch_logs_event(event):
    """Parse CloudWatch Logs event from subscription filter"""
    # CloudWatch Logs data is base64 encoded and gzipped
    compressed_payload = base64.b64decode(event['awslogs']['data'])
    uncompressed_payload = gzip.decompress(compressed_payload)
    log_data = json.loads(uncompressed_payload)

    return log_data

def extract_severity(message):
    """Extract severity from log message"""
    message_upper = message.upper()
    if 'CRITICAL' in message_upper:
        return 'CRITICAL'
    elif 'ERROR' in message_upper:
        return 'HIGH'
    elif 'WARN' in message_upper:
        return 'MEDIUM'
    else:
        return 'LOW'

def lambda_handler(event, context):
    """Ingestor - handles CloudWatch Logs events and sends alerts to SQS"""
    print(f"Received event type: {type(event)}")
    print(f"Event keys: {event.keys()}")

    queue_url = os.environ['PROCESSING_QUEUE_URL']

    # Handle CloudWatch Logs subscription filter events
    if 'awslogs' in event:
        log_data = parse_cloudwatch_logs_event(event)

        print(f"Log group: {log_data['logGroup']}")
        print(f"Log stream: {log_data['logStream']}")
        print(f"Number of log events: {len(log_data['logEvents'])}")

        # Process each log event
        for log_event in log_data['logEvents']:
            message_text = log_event['message']
            severity = extract_severity(message_text)

            # Create alert message
            alert_message = {
                'alert_id': log_event['id'],
                'message': message_text,
                'severity': severity,
                'source': 'cloudwatch_logs',
                'log_group': log_data['logGroup'],
                'log_stream': log_data['logStream'],
                'timestamp': log_event['timestamp']
            }

            print(f"Sending alert: {severity} - {message_text[:100]}...")

            # Send to processing queue
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(alert_message),
                MessageGroupId='alerts'
            )

        return {
            'statusCode': 200,
            'body': json.dumps(f'Processed {len(log_data["logEvents"])} log events')
        }

    # Handle EventBridge events (legacy support)
    elif 'detail' in event:
        detail = event.get('detail', {})
        message = {
            'alert_id': context.aws_request_id,
            'message': detail.get('message', 'Test alert'),
            'severity': detail.get('severity', 'HIGH'),
            'source': 'eventbridge',
            'log_group': detail.get('log_group', '/aws/test-app'),
                        'log_stream': detail.get('log_stream', 'test-stream'),
            'timestamp': int(datetime.utcnow().timestamp() * 1000)
        }

        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message),
            MessageGroupId='alerts'
        )

        return {'statusCode': 200, 'body': 'Alert sent'}

    # Handle manual test invocations
    else:
        print("Manual test invocation")
        message = {
            'alert_id': context.aws_request_id,
            'message': event.get('message', 'Manual test alert'),
            'severity': event.get('severity', 'HIGH'),
            'source': event.get('source', 'manual'),
            'log_group': event.get('log_group', '/aws/test-app'),  # Default to test app
            'log_stream': event.get('log_stream', 'test-stream'),
            'timestamp': int(datetime.utcnow().timestamp() * 1000)
        }

        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message),
            MessageGroupId='alerts'
        )

        return {'statusCode': 200, 'body': 'Test alert sent'}
