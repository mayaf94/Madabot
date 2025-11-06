# Jira Integration Setup Guide

This guide walks you through enabling Jira ticket creation from Slack alerts.

## Architecture Overview

When you click the "🎫 Create Jira" button in Slack:

```
Slack Button Click → API Gateway → Slack Interactions Lambda
                                           ↓
                                    Jira Queue (SQS)
                                           ↓
                                    Jira Notifier Lambda
                                           ↓
                                    Jira API (ticket created)
```

## Prerequisites

1. ✅ Jira Cloud account with API access
2. ✅ Jira project where tickets will be created
3. ✅ Jira API token
4. ✅ Slack App with bot token (already configured)
5. ✅ AWS account with deployed infrastructure

## Step 1: Get Jira Credentials

### 1.1 Create Jira API Token

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a name like "MCP First Responder"
4. Copy the token (you'll need it in Step 3)

### 1.2 Get Your Jira Details

You'll need:
- **Jira URL**: Your Jira instance URL (e.g., `https://your-company.atlassian.net`)
- **Project Key**: The project where tickets will be created (e.g., `INCIDENT`, `OPS`, `DEVOPS`)
- **Issue Type**: Type of ticket to create (usually `Task`, `Bug`, or `Incident`)

To find your project key:
1. Go to your Jira project
2. Look at the URL: `https://your-company.atlassian.net/browse/PROJECTKEY-123`
3. The part before the dash is your project key

## Step 2: Configure Terraform Variables

Edit `terraform/environments/dev.tfvars`:

```hcl
# Enable Jira integration
jira_enabled     = true
jira_url         = "https://your-company.atlassian.net"
jira_project_key = "OPS"              # Your project key
jira_issue_type  = "Task"             # or "Bug", "Incident", etc.

# Leave this empty - we'll set it via command line for security
jira_api_token   = ""
```

## Step 3: Store Jira API Token in AWS

```bash
# Set your AWS profile
export AWS_PROFILE=hakaton

# Store the Jira API token in AWS SSM Parameter Store (encrypted)
# Replace YOUR_JIRA_EMAIL and YOUR_JIRA_API_TOKEN with your actual credentials
aws ssm put-parameter \
  --name "/mcp-first-responder/dev/jira-api-token" \
  --description "Jira API token for creating tickets" \
  --type "SecureString" \
  --value "YOUR_JIRA_EMAIL:YOUR_JIRA_API_TOKEN" \
  --region us-east-1

# Example:
# aws ssm put-parameter \
#   --name "/mcp-first-responder/dev/jira-api-token" \
#   --type "SecureString" \
#   --value "maya@company.com:ATBBxxxxxxxxxxxxxxxx" \
#   --region us-east-1
```

**Note**: Jira API authentication format is `email:api_token`

## Step 4: Get Slack Signing Secret

The Slack Interactions handler needs to verify requests are actually from Slack.

1. Go to https://api.slack.com/apps
2. Select your app
3. Go to "Basic Information" → "App Credentials"
4. Copy the "Signing Secret"

### 4.1 Store Slack Signing Secret

```bash
export AWS_PROFILE=hakaton

aws secretsmanager create-secret \
  --name "slack-signing-secret" \
  --description "Slack signing secret for verifying interactive requests" \
  --secret-string '{"signing_secret":"YOUR_SLACK_SIGNING_SECRET"}' \
  --region us-east-1
```

## Step 5: Deploy with Terraform

```bash
cd terraform

# Plan the deployment
terraform plan -var-file=environments/dev.tfvars

# Expected changes:
# + Jira Queue (SQS FIFO)
# + Jira Notifier Lambda
# + Slack Interactions Lambda
# + API Gateway (HTTP API)
# + IAM permissions updates

# Apply the changes
terraform apply -var-file=environments/dev.tfvars
```

## Step 6: Configure Slack Interactivity

After deployment, get the API Gateway URL:

```bash
terraform output slack_interactions_url
```

**Example output**: `https://abc123xyz.execute-api.us-east-1.amazonaws.com/dev/slack/interactions`

### 6.1 Enable Interactivity in Slack

1. Go to https://api.slack.com/apps
2. Select your app
3. Go to "Interactivity & Shortcuts"
4. Toggle "Interactivity" to **ON**
5. In "Request URL", paste the URL from terraform output
6. Click "Save Changes"

### 6.2 Test the Endpoint

Slack will send a test request to verify the endpoint works. You should see:
- ✅ "Your URL didn't respond with the value of the `challenge` parameter"

If you see an error, check:
- Lambda logs: `aws logs tail /aws/lambda/mcp-first-responder-dev-slack-interactions --follow`
- API Gateway is deployed
- Lambda has permission to be invoked by API Gateway

## Step 7: Test the Integration

### 7.1 Generate a Test Alert

```bash
cd test
source venv/bin/activate
export AWS_PROFILE=hakaton
python test_app.py
```

### 7.2 Check Slack

Within 1-2 minutes, you should see an alert in `#pipline-monitoring` with:
- Severity indicator (color-coded)
- Alert details
- **✅ Acknowledge** button
- **🎫 Create Jira** button

### 7.3 Click "Create Jira" Button

1. Click the "🎫 Create Jira" button
2. You should see a message: "🎫 Jira ticket is being created by YOUR_NAME..."
3. Wait ~5-10 seconds

### 7.4 Verify Jira Ticket

1. Go to your Jira project
2. Look for a new ticket with:
   - Summary: Alert message
   - Description: Full alert details + AI analysis
   - Priority: Mapped from severity (CRITICAL → Highest, HIGH → High, etc.)
   - Labels: `automated-alert`, `severity-critical`, `mcp-first-responder`

## Monitoring & Debugging

### Check Slack Interactions Lambda Logs

```bash
export AWS_PROFILE=hakaton

aws logs tail /aws/lambda/mcp-first-responder-dev-slack-interactions --follow
```

Look for:
- ✅ "Creating Jira ticket for alert XXX"
- ✅ "Sent alert to Jira queue for processing"

### Check Jira Notifier Lambda Logs

```bash
aws logs tail /aws/lambda/mcp-first-responder-dev-jira-notifier --follow
```

Look for:
- ✅ "Creating Jira ticket in project OPS"
- ✅ "Jira ticket created: OPS-123 - https://..."

### Check Jira Queue

```bash
# Get queue URL
terraform output jira_queue_url

# Check queue depth
aws sqs get-queue-attributes \
  --queue-url $(terraform output -raw jira_queue_url) \
  --attribute-names ApproximateNumberOfMessagesVisible
```

## Troubleshooting

### Error: "Failed to create Jira ticket"

**Possible causes:**
1. Invalid Jira credentials
2. Project key doesn't exist
3. Issue type doesn't exist in the project
4. User doesn't have permission to create tickets

**Solution:**
```bash
# Test Jira API manually
curl -u "YOUR_EMAIL:YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  "https://your-company.atlassian.net/rest/api/2/project/OPS"

# Should return project details
# If it fails, check your credentials or project key
```

### Error: "Alert not found in database"

**Possible causes:**
- Alert was deleted from DynamoDB
- Alert ID is incorrect

**Solution:**
- Check DynamoDB: `aws dynamodb scan --table-name mcp-first-responder-dev-alerts --limit 10`
- Verify alert_id matches

### Slack Says "Invalid Request Signature"

**Possible causes:**
- Signing secret is incorrect
- Lambda doesn't have access to Secrets Manager

**Solution:**
```bash
# Verify signing secret
aws secretsmanager get-secret-value --secret-id slack-signing-secret

# Check Lambda has Secrets Manager permission
aws lambda get-policy --function-name mcp-first-responder-dev-slack-interactions
```

### No Response from Slack Button Click

**Possible causes:**
- API Gateway URL not configured in Slack
- Lambda timeout
- IAM permissions issue

**Solution:**
1. Verify API Gateway URL in Slack app settings
2. Check Lambda logs for errors
3. Increase Lambda timeout if needed

## Configuration Options

### Custom Issue Types

If your Jira project uses custom issue types (e.g., "Incident"), update `dev.tfvars`:

```hcl
jira_issue_type = "Incident"
```

Then re-apply Terraform:
```bash
terraform apply -var-file=environments/dev.tfvars
```

### Custom Fields

To add custom fields to Jira tickets, edit `lambdas/jira_notifier/handler.py`:

```python
issue_data = {
    "fields": {
        "project": {"key": jira_config['project_key']},
        "summary": f"[{severity}] {alert_message}",
        "description": format_jira_description(alert, analysis),
        "issuetype": {"name": jira_config['issue_type']},
        "priority": {"name": map_severity_to_jira_priority(severity)},

        # Add custom fields here
        "customfield_10001": "Production",  # Environment
        "customfield_10002": "High",        # Business Impact

        "labels": [...]
    }
}
```

To find custom field IDs:
```bash
curl -u "YOUR_EMAIL:YOUR_API_TOKEN" \
  "https://your-company.atlassian.net/rest/api/2/field"
```

### Multiple Projects

To route different severities to different projects, edit `lambdas/jira_notifier/handler.py`:

```python
# Route by severity
severity_projects = {
    'CRITICAL': 'INCIDENT',
    'HIGH': 'INCIDENT',
    'MEDIUM': 'OPS',
    'LOW': 'OPS'
}

project_key = severity_projects.get(severity, 'OPS')
```

## Architecture Details

### Components Created

1. **Jira Queue (SQS FIFO)**:
   - Queues alerts for Jira ticket creation
   - FIFO ensures ordered processing
   - DLQ for failed ticket creations

2. **Jira Notifier Lambda**:
   - Listens to Jira queue
   - Retrieves API token from SSM
   - Creates Jira tickets via REST API
   - 512MB memory, 5min timeout

3. **Slack Interactions Lambda**:
   - Receives button clicks via API Gateway
   - Verifies Slack signature
   - Retrieves alert from DynamoDB
   - Sends to Jira queue
   - 512MB memory, 30sec timeout

4. **API Gateway (HTTP API)**:
   - Public endpoint for Slack webhooks
   - Routes to Slack Interactions Lambda
   - No authentication (relies on Slack signature verification)

### Security

- ✅ Jira API token stored encrypted in SSM Parameter Store
- ✅ Slack signing secret stored in Secrets Manager
- ✅ Request signature verification prevents unauthorized access
- ✅ Least-privilege IAM roles
- ✅ VPC not required (Lambdas access AWS services via AWS network)

### Cost Estimate

**With Jira enabled** (assuming 100 alerts/month, 50% create Jira tickets):

| Service | Cost/Month |
|---------|-----------|
| Jira Notifier Lambda | ~$1 |
| Slack Interactions Lambda | ~$0.50 |
| API Gateway (HTTP API) | ~$0.20 |
| SQS Jira Queue | ~$0.001 |
| **Additional Total** | **~$1.70/month** |

Very minimal additional cost! 💰

## Next Steps

- ✅ Test with different severity levels
- ✅ Customize Jira ticket templates
- ✅ Add custom fields if needed
- ✅ Set up Jira automation rules (auto-assign, notifications, etc.)
- ✅ Monitor Jira queue and DLQ
- 📊 Create dashboard for Jira ticket metrics

## Support

For issues:
1. Check Lambda logs (Slack Interactions + Jira Notifier)
2. Check Jira queue depth
3. Verify Jira credentials
4. Test Jira API manually
5. Check API Gateway access logs

---

**Congratulations!** 🎉 You now have full Jira integration with your alert system!
