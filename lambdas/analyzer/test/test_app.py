#!/usr/bin/env python3
"""
Simple test application that generates various log levels to CloudWatch Logs.
This triggers the MCP First-Responder alert system.
"""

import time
import logging
import random
import watchtower
import boto3

# Configure CloudWatch Logs handler
cloudwatch_client = boto3.client('logs', region_name='us-east-1')

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add CloudWatch handler with formatter
cw_handler = watchtower.CloudWatchLogHandler(
    log_group='/aws/test-app',
    stream_name='test-stream',
    boto3_client=cloudwatch_client,
    create_log_group=True
)
cw_handler.setLevel(logging.DEBUG)

# Add formatter that includes log level in the message
cw_formatter = logging.Formatter('[%(levelname)s] %(message)s')
cw_handler.setFormatter(cw_formatter)

# Add console handler for local visibility
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

logger.addHandler(cw_handler)
logger.addHandler(console_handler)

# Test scenarios
def generate_error_scenarios():
    """Generate various error scenarios to test alert system"""

    scenarios = [
        {
            'level': 'ERROR',
            'message': 'Database connection failed: Connection timeout after 30s',
            'exception': 'psycopg2.OperationalError: could not connect to server'
        },
        {
            'level': 'CRITICAL',
            'message': 'Out of memory error in payment processing',
            'exception': 'MemoryError: Unable to allocate 512MB for transaction batch'
        },
        {
            'level': 'ERROR',
            'message': 'API request failed: External service timeout',
            'exception': 'requests.exceptions.Timeout: Request to https://api.example.com/v1/users timed out'
        },
        {
            'level': 'WARNING',
            'message': 'High CPU usage detected: 95% sustained over 5 minutes',
            'exception': None
        },
        {
            'level': 'ERROR',
            'message': 'S3 upload failed: Access denied',
            'exception': 'botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the PutObject operation'
        },
        {
            'level': 'CRITICAL',
            'message': 'Redis cache cluster unavailable',
            'exception': 'redis.exceptions.ConnectionError: Error connecting to Redis on localhost:6379'
        }
    ]

    return random.choice(scenarios)

def main():
    """Main application loop"""

    print("Starting test application...")
    print("Log Group: /aws/test-app")
    print("Generating logs every 30 seconds...")
    print("Press Ctrl+C to stop\n")

    logger.info("Test application started successfully")

    iteration = 0

    try:
        while True:
            iteration += 1

            # Generate normal info logs most of the time
            if iteration % 3 == 0:
                # Every 3rd iteration, generate an error
                scenario = generate_error_scenarios()

                if scenario['level'] == 'ERROR':
                    logger.error(f"{scenario['message']}\n{scenario['exception']}")
                elif scenario['level'] == 'CRITICAL':
                    logger.critical(f"{scenario['message']}\n{scenario['exception']}")
                elif scenario['level'] == 'WARNING':
                    logger.warning(scenario['message'])

                print(f"✗ Generated {scenario['level']} log")
            else:
                # Normal operation logs
                logger.info(f"Processing request #{iteration} - Status: OK")
                print(f"✓ Generated INFO log #{iteration}")

            # Wait 30 seconds between logs
            time.sleep(30)

    except KeyboardInterrupt:
        logger.info("Test application shutting down")
        print("\n\nShutting down gracefully...")
        # Give CloudWatch handler time to flush
        time.sleep(2)

if __name__ == '__main__':
    main()
