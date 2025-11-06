# Lambda Function Outputs
output "ingestor_function_name" {
  description = "Name of the ingestor Lambda function"
  value       = module.lambda_ingestor.function_name
}

output "ingestor_function_arn" {
  description = "ARN of the ingestor Lambda function"
  value       = module.lambda_ingestor.function_arn
}

output "analyzer_function_name" {
  description = "Name of the analyzer Lambda function"
  value       = module.lambda_analyzer.function_name
}

output "analyzer_function_arn" {
  description = "ARN of the analyzer Lambda function"
  value       = module.lambda_analyzer.function_arn
}

output "slack_notifier_function_name" {
  description = "Name of the Slack notifier Lambda function"
  value       = module.lambda_slack_notifier.function_name
}

output "slack_notifier_function_arn" {
  description = "ARN of the Slack notifier Lambda function"
  value       = module.lambda_slack_notifier.function_arn
}

# SQS Queue Outputs
output "processing_queue_url" {
  description = "URL of the processing queue"
  value       = module.sqs_processing.queue_url
}

output "processing_queue_arn" {
  description = "ARN of the processing queue"
  value       = module.sqs_processing.queue_arn
}

output "distribution_queue_url" {
  description = "URL of the distribution queue"
  value       = module.sqs_distribution.queue_url
}

output "distribution_queue_arn" {
  description = "ARN of the distribution queue"
  value       = module.sqs_distribution.queue_arn
}

output "processing_dlq_url" {
  description = "URL of the processing dead letter queue"
  value       = module.sqs_processing.dlq_url
}

output "distribution_dlq_url" {
  description = "URL of the distribution dead letter queue"
  value       = module.sqs_distribution.dlq_url
}

# DynamoDB Table Outputs
output "alerts_table_name" {
  description = "Name of the alerts DynamoDB table"
  value       = module.dynamodb_alerts.table_name
}

output "alerts_table_arn" {
  description = "ARN of the alerts DynamoDB table"
  value       = module.dynamodb_alerts.table_arn
}

output "analysis_cache_table_name" {
  description = "Name of the analysis cache DynamoDB table"
  value       = module.dynamodb_cache.table_name
}

output "analysis_cache_table_arn" {
  description = "ARN of the analysis cache DynamoDB table"
  value       = module.dynamodb_cache.table_arn
}

# EventBridge Outputs
output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule"
  value       = module.eventbridge.rule_name
}

output "eventbridge_rule_arn" {
  description = "ARN of the EventBridge rule"
  value       = module.eventbridge.rule_arn
}

# AI Provider Output
output "ai_provider" {
  description = "AI provider being used (anthropic or google)"
  value       = var.ai_provider
}

# SSM Parameter Outputs (names only, not values)
output "ai_api_key_parameter" {
  description = "SSM Parameter Store name for AI API key"
  value       = var.ai_provider == "anthropic" ? aws_ssm_parameter.anthropic_api_key[0].name : aws_ssm_parameter.google_api_key[0].name
}

output "slack_bot_token_secret_name" {
  description = "Secrets Manager secret name for Slack bot token"
  value       = data.aws_secretsmanager_secret.slack_bot_token.name
}

# IAM Role Outputs
output "ingestor_role_arn" {
  description = "ARN of the ingestor Lambda IAM role"
  value       = module.iam_ingestor.role_arn
}

output "analyzer_role_arn" {
  description = "ARN of the analyzer Lambda IAM role"
  value       = module.iam_analyzer.role_arn
}

output "notifier_role_arn" {
  description = "ARN of the notifier Lambda IAM role"
  value       = module.iam_notifier.role_arn
}

# CloudWatch Log Groups
output "ingestor_log_group" {
  description = "CloudWatch log group for ingestor Lambda"
  value       = "/aws/lambda/${module.lambda_ingestor.function_name}"
}

output "analyzer_log_group" {
  description = "CloudWatch log group for analyzer Lambda"
  value       = "/aws/lambda/${module.lambda_analyzer.function_name}"
}

output "notifier_log_group" {
  description = "CloudWatch log group for notifier Lambdas"
  value       = "/aws/lambda/${module.lambda_slack_notifier.function_name}"
}

# Deployment Information
output "environment" {
  description = "Deployment environment"
  value       = var.environment
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "project_name" {
  description = "Project name"
  value       = var.project_name
}

# Monitoring URLs
output "cloudwatch_dashboard_url" {
  description = "URL to CloudWatch dashboard (manual creation required)"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:"
}

output "lambda_console_url" {
  description = "URL to Lambda console"
  value       = "https://${var.aws_region}.console.aws.amazon.com/lambda/home?region=${var.aws_region}#/functions"
}

output "dynamodb_console_url" {
  description = "URL to DynamoDB console"
  value       = "https://${var.aws_region}.console.aws.amazon.com/dynamodbv2/home?region=${var.aws_region}#tables"
}

# Quick Start Commands
output "test_command" {
  description = "Command to test the ingestor Lambda"
  value       = "aws lambda invoke --function-name ${module.lambda_ingestor.function_name} --payload file://test-event.json response.json"
}

output "view_logs_ingestor" {
  description = "Command to view ingestor logs"
  value       = "aws logs tail /aws/lambda/${module.lambda_ingestor.function_name} --follow"
}

output "view_logs_analyzer" {
  description = "Command to view analyzer logs"
  value       = "aws logs tail /aws/lambda/${module.lambda_analyzer.function_name} --follow"
}

output "check_dlq_processing" {
  description = "Command to check processing DLQ"
  value       = "aws sqs receive-message --queue-url ${module.sqs_processing.dlq_url} --max-number-of-messages 10"
}

output "check_queue_depth" {
  description = "Command to check processing queue depth"
  value       = "aws sqs get-queue-attributes --queue-url ${module.sqs_processing.queue_url} --attribute-names ApproximateNumberOfMessagesVisible"
}