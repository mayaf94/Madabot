# TODO: Complete Jira Integration

## Current Status: 90% Complete ✅

Most infrastructure is deployed and working. Only a few final steps remain to make the "Create Jira" button functional.

---

## ✅ What's Already Done

### Code & Configuration
- ✅ Jira Notifier Lambda created (`lambdas/jira_notifier/handler.py`)
- ✅ Slack Interactions Lambda created (`lambdas/slack_interactions/handler.py`)
- ✅ Fixed Jira authentication (Basic Auth with base64 encoding)
- ✅ Terraform configuration updated with all Jira resources
- ✅ Slack notifier updated with proper environment variables

### AWS Resources Created
- ✅ Jira Queue (SQS FIFO): `mcp-first-responder-dev-jira-queue.fifo`
- ✅ Jira DLQ (SQS FIFO): `mcp-first-responder-dev-jira-dlq.fifo`
- ✅ Slack Interactions Lambda: `mcp-first-responder-dev-slack-interactions`
- ✅ API Gateway: `mcp-first-responder-dev-slack-interactions`
- ✅ API Gateway Route: `POST /slack/interactions`

### Secrets & Credentials
- ✅ Jira API token stored in AWS SSM: `/mcp-first-responder/dev/jira-api-token`
  - Format: `maya.faerman@develeap.com:ATATT3x...`
- ✅ Slack bot token stored in Secrets Manager: `slack-bot-token`
- ✅ Slack signing secret stored in Secrets Manager: `slack-signing-secret`

### Configuration
- ✅ Jira project verified: `SCRUM` at https://madabot-team.atlassian.net
- ✅ Jira API tested: Can create tickets successfully (SCRUM-6 created)
- ✅ Slack channel configured: `#pipline-monitoring`

---

## 🔧 What Still Needs to Be Done

### 1. Fix Terraform SSM Parameter Issue (5 minutes)

**Problem**: Terraform tried to create `/mcp-first-responder/dev/jira-api-token` but it already exists (we created it manually).

**Solution**: Import the existing parameter into Terraform state.

```bash
export AWS_PROFILE=hakaton
cd terraform

# Import the existing SSM parameter
terraform import 'aws_ssm_parameter.jira_api_token[0]' '/mcp-first-responder/dev/jira-api-token'

# Complete the deployment
terraform apply -var-file=environments/dev.tfvars
```

**Expected Result**:
- Jira Notifier Lambda deployed
- Lambda event source mapping created (Jira Queue → Lambda)

---

### 2. Get API Gateway URL (1 minute)

After Terraform completes successfully:

```bash
cd terraform
terraform output slack_interactions_url
```

**Expected Output**:
```
https://abc123xyz.execute-api.us-east-1.amazonaws.com/dev/slack/interactions
```

**Copy this URL** - you'll need it for the next step.

---

### 3. Configure Slack App Interactivity (3 minutes)

1. Go to https://api.slack.com/apps
2. Select your app
3. Click **"Interactivity & Shortcuts"** in the left sidebar
4. Toggle **"Interactivity"** to **ON**
5. In **"Request URL"**, paste the API Gateway URL from step 2
6. Click **"Save Changes"**

**Slack will verify the endpoint**:
- ✅ Success: "Your URL was verified"
- ❌ Failure: Check Lambda logs

If verification fails:
```bash
# Check Slack Interactions Lambda logs
aws logs tail /aws/lambda/mcp-first-responder-dev-slack-interactions --follow
```

---

### 4. Save Alert to DynamoDB (10 minutes)

**Problem**: The Slack Interactions Lambda retrieves alerts from DynamoDB, but the Analyzer Lambda doesn't save them there yet.

**Solution**: Update the Analyzer Lambda to save alerts to DynamoDB.

#### Edit `lambdas/analyzer/handler.py`

Add after line 10:
```python
dynamodb = boto3.resource('dynamodb')
```

Add this function after line 11:
```python
def save_alert_to_dynamodb(alert_data, analysis):
    """Save alert and analysis to DynamoDB"""
    try:
        table_name = os.environ.get('ALERTS_TABLE')
        table = dynamodb.Table(table_name)

        item = {
            'alert_id': alert_data.get('alert_id'),
            'timestamp': alert_data.get('timestamp', int(datetime.now().timestamp() * 1000)),
            'severity': alert_data.get('severity', 'UNKNOWN'),
            'source': alert_data.get('source', 'unknown'),
            'alert': alert_data.get('message', ''),
            'analysis': analysis,
            'log_group': alert_data.get('log_group', ''),
            'log_stream': alert_data.get('log_stream', ''),
            'infrastructure_context': alert_data.get('infrastructure_context', {}),
            'model': 'gemini-2.5-flash'
        }

        table.put_item(Item=item)
        print(f"✅ Saved alert {alert_data.get('alert_id')} to DynamoDB")
        return True
    except Exception as e:
        print(f"❌ Error saving to DynamoDB: {e}")
        return False
```

Add import at the top:
```python
from datetime import datetime
```

Then call this function in the handler around line 112, after getting the analysis:
```python
# Save to DynamoDB
save_alert_to_dynamodb(body, analysis)
```

After editing, deploy:
```bash
cd terraform
terraform apply -var-file=environments/dev.tfvars
```

---

### 5. Test End-to-End (5 minutes)

#### Generate a Test Alert

```bash
cd test
source venv/bin/activate
export AWS_PROFILE=hakaton
python test_app.py
```

#### Verify the Flow

1. **Wait 1-2 minutes** for alert to appear in Slack
2. Check `#pipline-monitoring` channel
3. You should see:
   - 🎨 Color-coded alert
   - Alert details
   - AI analysis
   - ✅ Acknowledge button
   - 🎫 Create Jira button
4. **Click "🎫 Create Jira"**
5. You should see: "🎫 Jira ticket is being created by YOUR_NAME..."
6. **Wait 5-10 seconds**
7. Check Jira backlog: https://madabot-team.atlassian.net/jira/software/projects/SCRUM/boards/1/backlog
8. New ticket should appear (SCRUM-7, SCRUM-8, etc.)

---

## 🐛 Troubleshooting

### If Slack Button Does Nothing

**Check Slack Interactions Lambda logs:**
```bash
aws logs tail /aws/lambda/mcp-first-responder-dev-slack-interactions --follow --profile hakaton
```

**Look for:**
- ✅ "Creating Jira ticket for alert XXX"
- ✅ "Sent alert to Jira queue"
- ❌ "Alert not found in database" → DynamoDB save issue (see step 4)
- ❌ "Invalid request signature" → Slack signing secret issue

### If Jira Ticket Not Created

**Check Jira Notifier Lambda logs:**
```bash
aws logs tail /aws/lambda/mcp-first-responder-dev-jira-notifier --follow --profile hakaton
```

**Look for:**
- ✅ "Creating Jira ticket in project SCRUM"
- ✅ "Jira ticket created: SCRUM-X"
- ❌ "Failed to retrieve Jira API token" → SSM parameter issue
- ❌ HTTP 401/403 → Jira credentials issue

**Check Jira Queue:**
```bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/006262944085/mcp-first-responder-dev-jira-queue.fifo \
  --attribute-names ApproximateNumberOfMessagesVisible \
  --profile hakaton
```

If messages are stuck in queue → Jira Lambda has an error

### If API Gateway Verification Fails

**Check:**
1. Lambda has permission to be invoked by API Gateway (should be auto-created)
2. Lambda function exists: `mcp-first-responder-dev-slack-interactions`
3. Slack signing secret is correct in Secrets Manager

---

## 📊 Monitoring Commands

```bash
# Watch all Lambda logs in parallel (requires 3 terminals)
aws logs tail /aws/lambda/mcp-first-responder-dev-ingestor --follow --profile hakaton
aws logs tail /aws/lambda/mcp-first-responder-dev-analyzer --follow --profile hakaton
aws logs tail /aws/lambda/mcp-first-responder-dev-slack-notifier --follow --profile hakaton
aws logs tail /aws/lambda/mcp-first-responder-dev-slack-interactions --follow --profile hakaton
aws logs tail /aws/lambda/mcp-first-responder-dev-jira-notifier --follow --profile hakaton

# Check queue depths
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/006262944085/mcp-first-responder-dev-processing-queue.fifo \
  --attribute-names ApproximateNumberOfMessagesVisible \
  --profile hakaton

# Check DynamoDB for alerts
aws dynamodb scan \
  --table-name mcp-first-responder-dev-alerts \
  --limit 5 \
  --profile hakaton
```

---

## 🎯 Success Criteria

When everything is working, you should see:

1. ✅ Test app generates error in CloudWatch
2. ✅ Alert appears in Slack within 1-2 minutes
3. ✅ Alert has "Create Jira" button
4. ✅ Clicking button shows "Jira ticket is being created..."
5. ✅ Ticket appears in Jira backlog within 10 seconds
6. ✅ Ticket has:
   - Summary: Alert message
   - Description: Full context + AI analysis
   - Priority: Mapped from severity
   - Labels: `automated-alert`, `mcp-first-responder`

---

## 📝 Quick Command Reference

```bash
# Set AWS profile (run this in every terminal)
export AWS_PROFILE=hakaton

# Deploy infrastructure
cd terraform
terraform apply -var-file=environments/dev.tfvars

# Get API Gateway URL
terraform output slack_interactions_url

# Generate test alert
cd test
source venv/bin/activate
python test_app.py

# Check specific Lambda logs
aws logs tail /aws/lambda/mcp-first-responder-dev-[LAMBDA_NAME] --follow

# Check queue depth
terraform output jira_queue_url
aws sqs get-queue-attributes --queue-url [URL] --attribute-names ApproximateNumberOfMessagesVisible
```

---

## 🔐 Credentials Reference

All credentials are stored securely in AWS:

| Type | Location | Name |
|------|----------|------|
| Jira API Token | SSM Parameter Store | `/mcp-first-responder/dev/jira-api-token` |
| Slack Bot Token | Secrets Manager | `slack-bot-token` |
| Slack Signing Secret | Secrets Manager | `slack-signing-secret` |
| Google API Key | SSM Parameter Store | `/mcp-first-responder/dev/google-api-key` |

---

## 🎉 When Complete

Once everything works:
1. Document any issues you encountered
2. Update JIRA_INTEGRATION_GUIDE.md if needed
3. Commit and push any code changes
4. Celebrate! 🎊

---

**Estimated Time to Complete**: 20-25 minutes

**Last Updated**: 2025-11-06
**Status**: Ready for final deployment steps
