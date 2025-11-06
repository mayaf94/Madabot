# Core Variables
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "mcp-first-responder"
}

variable "owner_email" {
  description = "Email of the project owner for tagging"
  type        = string
}

# AI Provider Configuration
variable "ai_provider" {
  description = "AI provider to use for analysis (anthropic or google)"
  type        = string
  default     = "anthropic"
  validation {
    condition     = contains(["anthropic", "google"], var.ai_provider)
    error_message = "AI provider must be 'anthropic' (Claude) or 'google' (Gemini)."
  }
}

# Secrets Configuration
variable "anthropic_api_key" {
  description = "Anthropic API key for Claude (stored in SSM Parameter Store)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "google_api_key" {
  description = "Google API key for Gemini (stored in SSM Parameter Store)"
  type        = string
  sensitive   = true
  default     = ""
}

# Slack bot token is now stored in AWS Secrets Manager (slack-bot-token)
# No variable needed for token - Terraform references the existing secret

variable "slack_channel" {
  description = "Slack channel to send alerts to (e.g., #alerts or C01234ABCD)"
  type        = string
  default     = "#alerts"
}

variable "jira_enabled" {
  description = "Enable Jira integration"
  type        = bool
  default     = false
}

variable "jira_url" {
  description = "Jira instance URL"
  type        = string
  default     = ""
}

variable "jira_api_token" {
  description = "Jira API token (stored in SSM Parameter Store)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "jira_project_key" {
  description = "Jira project key for ticket creation"
  type        = string
  default     = ""
}

variable "email_enabled" {
  description = "Enable email notifications via SES"
  type        = bool
  default     = false
}

variable "email_from_address" {
  description = "Email sender address (must be verified in SES)"
  type        = string
  default     = ""
}

variable "email_to_addresses" {
  description = "Comma-separated list of recipient email addresses"
  type        = string
  default     = ""
}

# Lambda Configuration
variable "lambda_runtime" {
  description = "Python runtime version for Lambda functions"
  type        = string
  default     = "python3.11"
}

variable "ingestor_memory_size" {
  description = "Memory size (MB) for ingestor Lambda"
  type        = number
  default     = 512
}

variable "ingestor_timeout" {
  description = "Timeout (seconds) for ingestor Lambda"
  type        = number
  default     = 300
}

variable "analyzer_memory_size" {
  description = "Memory size (MB) for analyzer Lambda"
  type        = number
  default     = 1024
}

variable "analyzer_timeout" {
  description = "Timeout (seconds) for analyzer Lambda (needs time for Claude API)"
  type        = number
  default     = 900
}

variable "notifier_memory_size" {
  description = "Memory size (MB) for notifier Lambdas"
  type        = number
  default     = 512
}

variable "notifier_timeout" {
  description = "Timeout (seconds) for notifier Lambdas"
  type        = number
  default     = 300
}

# SQS Configuration
variable "processing_queue_visibility_timeout" {
  description = "Visibility timeout (seconds) for processing queue"
  type        = number
  default     = 900
}

variable "processing_queue_max_receive_count" {
  description = "Max receive count before moving to DLQ"
  type        = number
  default     = 3
}

variable "distribution_queue_visibility_timeout" {
  description = "Visibility timeout (seconds) for distribution queue"
  type        = number
  default     = 300
}

variable "distribution_queue_max_receive_count" {
  description = "Max receive count before moving to DLQ"
  type        = number
  default     = 3
}

variable "dlq_retention_period" {
  description = "Message retention period (seconds) for dead letter queues"
  type        = number
  default     = 1209600 # 14 days
}

# DynamoDB Configuration
variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode (PAY_PER_REQUEST or PROVISIONED)"
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "cache_ttl_hours" {
  description = "TTL in hours for analysis cache entries"
  type        = number
  default     = 24
}

# EventBridge Configuration
variable "eventbridge_rule_state" {
  description = "State of EventBridge rule (ENABLED or DISABLED)"
  type        = string
  default     = "ENABLED"
  validation {
    condition     = contains(["ENABLED", "DISABLED"], var.eventbridge_rule_state)
    error_message = "EventBridge rule state must be ENABLED or DISABLED."
  }
}

variable "cloudwatch_log_group_patterns" {
  description = "List of CloudWatch log group patterns to monitor"
  type        = list(string)
  default     = ["/aws/lambda/*"]
}

# CloudWatch Logs Subscription Filter Configuration
variable "enable_test_app_monitoring" {
  description = "Enable monitoring for test application log group"
  type        = bool
  default     = true
}

variable "enable_lambda_monitoring" {
  description = "Enable monitoring for Lambda function log groups"
  type        = bool
  default     = false
}

variable "monitored_lambda_patterns" {
  description = "List of Lambda log groups to monitor for errors"
  type        = list(string)
  default     = []
}

# Monitoring Configuration
variable "enable_cloudwatch_alarms" {
  description = "Enable CloudWatch alarms for monitoring"
  type        = bool
  default     = true
}

variable "dlq_alarm_threshold" {
  description = "Number of messages in DLQ to trigger alarm"
  type        = number
  default     = 1
}

variable "lambda_error_rate_threshold" {
  description = "Lambda error rate percentage to trigger alarm"
  type        = number
  default     = 5
}

# Tags
variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}