# Local variables for resource naming and common configurations
locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.additional_tags
  )

  lambda_source_dir = "${path.module}/../lambdas"
}

# SSM Parameters for Secrets Management
resource "aws_ssm_parameter" "anthropic_api_key" {
  count = var.ai_provider == "anthropic" ? 1 : 0

  name        = "/${var.project_name}/${var.environment}/anthropic-api-key"
  description = "Anthropic API key for Claude"
  type        = "SecureString"
  value       = var.anthropic_api_key

  tags = local.common_tags
}

resource "aws_ssm_parameter" "google_api_key" {
  count = var.ai_provider == "google" ? 1 : 0

  name        = "/${var.project_name}/${var.environment}/google-api-key"
  description = "Google API key for Gemini"
  type        = "SecureString"
  value       = var.google_api_key

  tags = local.common_tags
}

# Reference existing Secrets Manager secret for Slack webhook
data "aws_secretsmanager_secret" "slack_bot_token" {
  name = "slack-bot-token"
}

data "aws_secretsmanager_secret_version" "slack_bot_token" {
  secret_id = data.aws_secretsmanager_secret.slack_bot_token.id
}

resource "aws_ssm_parameter" "jira_api_token" {
  count = var.jira_enabled ? 1 : 0

  name        = "/${var.project_name}/${var.environment}/jira-api-token"
  description = "Jira API token"
  type        = "SecureString"
  value       = var.jira_api_token

  tags = local.common_tags
}

# DynamoDB Tables
module "dynamodb_alerts" {
  source = "./modules/dynamodb"

  table_name   = "${local.name_prefix}-alerts"
  billing_mode = var.dynamodb_billing_mode

  hash_key      = "alert_id"
  hash_key_type = "S"

  attributes = [
    {
      name = "alert_id"
      type = "S"
    },
    {
      name = "severity"
      type = "S"
    },
    {
      name = "timestamp"
      type = "N"
    }
  ]

  global_secondary_indexes = [
    {
      name            = "severity-timestamp-index"
      hash_key        = "severity"
      range_key       = "timestamp"
      projection_type = "ALL"
    }
  ]

  enable_streams   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  enable_ttl = false

  tags = local.common_tags
}

module "dynamodb_cache" {
  source = "./modules/dynamodb"

  table_name   = "${local.name_prefix}-analysis-cache"
  billing_mode = var.dynamodb_billing_mode

  hash_key      = "error_signature"
  hash_key_type = "S"

  attributes = [
    {
      name = "error_signature"
      type = "S"
    }
  ]

  global_secondary_indexes = []

  enable_streams = false

  enable_ttl         = true
  ttl_attribute_name = "ttl"

  tags = local.common_tags
}

# SQS Queues
module "sqs_processing" {
  source = "./modules/sqs"

  queue_name                  = "${local.name_prefix}-processing-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  visibility_timeout_seconds  = var.processing_queue_visibility_timeout

  enable_dlq           = true
  dlq_name             = "${local.name_prefix}-processing-dlq.fifo"
  max_receive_count    = var.processing_queue_max_receive_count
  dlq_retention_period = var.dlq_retention_period

  tags = local.common_tags
}

module "sqs_distribution" {
  source = "./modules/sqs"

  queue_name                  = "${local.name_prefix}-distribution-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  visibility_timeout_seconds  = var.distribution_queue_visibility_timeout

  enable_dlq           = true
  dlq_name             = "${local.name_prefix}-distribution-dlq.fifo"
  max_receive_count    = var.distribution_queue_max_receive_count
  dlq_retention_period = var.dlq_retention_period

  tags = local.common_tags
}

# Jira Processing Queue (only created if Jira is enabled)
module "sqs_jira" {
  count  = var.jira_enabled ? 1 : 0
  source = "./modules/sqs"

  queue_name                  = "${local.name_prefix}-jira-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  visibility_timeout_seconds  = 300

  enable_dlq           = true
  dlq_name             = "${local.name_prefix}-jira-dlq.fifo"
  max_receive_count    = 3
  dlq_retention_period = var.dlq_retention_period

  tags = local.common_tags
}

# IAM Roles for Lambda Functions
module "iam_ingestor" {
  source = "./modules/iam"

  role_name = "${local.name_prefix}-ingestor-role"
  service   = "lambda.amazonaws.com"

  policy_arns = [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  ]

  inline_policies = [
    {
      name = "ingestor-permissions"
      policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Effect = "Allow"
            Action = [
              "sqs:SendMessage",
              "sqs:GetQueueAttributes"
            ]
            Resource = module.sqs_processing.queue_arn
          }
        ]
      })
    }
  ]

  tags = local.common_tags
}

module "iam_analyzer" {
  source = "./modules/iam"

  role_name = "${local.name_prefix}-analyzer-role"
  service   = "lambda.amazonaws.com"

  policy_arns = [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  ]

  inline_policies = [
    {
      name = "analyzer-permissions"
      policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Effect = "Allow"
            Action = [
              "sqs:ReceiveMessage",
              "sqs:DeleteMessage",
              "sqs:GetQueueAttributes"
            ]
            Resource = module.sqs_processing.queue_arn
          },
          {
            Effect = "Allow"
            Action = [
              "sqs:SendMessage",
              "sqs:GetQueueAttributes"
            ]
            Resource = module.sqs_distribution.queue_arn
          },
          {
            Effect = "Allow"
            Action = [
              "dynamodb:GetItem",
              "dynamodb:PutItem",
              "dynamodb:UpdateItem",
              "dynamodb:Query",
              "dynamodb:Scan"
            ]
            Resource = [
              module.dynamodb_alerts.table_arn,
              "${module.dynamodb_alerts.table_arn}/index/*",
              module.dynamodb_cache.table_arn
            ]
          },
          {
            Effect = "Allow"
            Action = [
              "logs:FilterLogEvents",
              "logs:GetLogEvents",
              "logs:DescribeLogGroups",
              "logs:DescribeLogStreams"
            ]
            Resource = "*"
          },
          {
            Effect = "Allow"
            Action = [
              "ssm:GetParameter",
              "ssm:GetParameters"
            ]
            Resource = concat(
              var.ai_provider == "anthropic" ? [aws_ssm_parameter.anthropic_api_key[0].arn] : [],
              var.ai_provider == "google" ? [aws_ssm_parameter.google_api_key[0].arn] : []
            )
          },
          {
            Effect   = "Allow"
            Action   = [
              "ec2:DescribeInstanceStatus",
              "ec2:DescribeInstances",
              "ec2:DescribeTags"
            ]
            Resource = "*"
          },
          {
            Effect   = "Allow"
            Action   = [
              "ecs:ListClusters",
              "ecs:DescribeTasks",
              "ecs:DescribeContainerInstances",
              "ecs:DescribeServices"
            ]
            Resource = "*"
          },
          {
            Effect   = "Allow"
            Action   = [
              "elasticloadbalancing:DescribeLoadBalancers",
              "elasticloadbalancing:DescribeTargetGroups",
              "elasticloadbalancing:DescribeTargetHealth",
              "elasticloadbalancing:DescribeListeners"
            ]
            Resource = "*"
          },
          {
            Effect   = "Allow"
            Action   = [
              "cloudformation:ListStacks",
              "cloudformation:DescribeStacks",
              "cloudformation:DescribeStackEvents",
              "cloudformation:DescribeStackResources"
            ]
            Resource = "*"
          },
          {
            Effect   = "Allow"
            Action   = [
              "cloudwatch:GetMetricStatistics",
              "cloudwatch:GetMetricData",
              "cloudwatch:ListMetrics"
            ]
            Resource = "*"
          }
        ]
      })
    }
  ]

  tags = local.common_tags
}

module "iam_notifier" {
  source = "./modules/iam"

  role_name = "${local.name_prefix}-notifier-role"
  service   = "lambda.amazonaws.com"

  policy_arns = [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  ]

  inline_policies = [
    {
      name = "notifier-permissions"
      policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Effect = "Allow"
            Action = [
              "sqs:ReceiveMessage",
              "sqs:DeleteMessage",
              "sqs:GetQueueAttributes"
            ]
            Resource = concat(
              [module.sqs_distribution.queue_arn],
              var.jira_enabled ? [module.sqs_jira[0].queue_arn] : []
            )
          },
          {
            Effect = "Allow"
            Action = [
              "sqs:SendMessage"
            ]
            Resource = var.jira_enabled ? module.sqs_jira[0].queue_arn : ""
            Condition = var.jira_enabled ? {} : null
          },
          {
            Effect = "Allow"
            Action = [
              "dynamodb:GetItem",
              "dynamodb:Query"
            ]
            Resource = module.dynamodb_alerts.table_arn
          },
          {
            Effect = "Allow"
            Action = [
              "secretsmanager:GetSecretValue"
            ]
            Resource = [
              data.aws_secretsmanager_secret.slack_bot_token.arn
            ]
          },
          {
            Effect = "Allow"
            Action = [
              "ssm:GetParameter",
              "ssm:GetParameters"
            ]
            Resource = var.jira_enabled ? [
              aws_ssm_parameter.jira_api_token[0].arn
            ] : []
          },
          {
            Effect = "Allow"
            Action = [
              "ses:SendEmail",
              "ses:SendRawEmail"
            ]
            Resource = "*"
            Condition = {
              StringEquals = {
                "ses:FromAddress" = var.email_enabled ? var.email_from_address : ""
              }
            }
          }
        ]
      })
    }
  ]

  tags = local.common_tags
}

# Lambda Functions
module "lambda_ingestor" {
  source = "./modules/lambda"

  function_name = "${local.name_prefix}-ingestor"
  description   = "Ingests and normalizes alerts from CloudWatch"
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime

  source_dir = "${local.lambda_source_dir}/ingestor"

  role_arn = module.iam_ingestor.role_arn

  memory_size = var.ingestor_memory_size
  timeout     = var.ingestor_timeout

  environment_variables = {
    ENVIRONMENT          = var.environment
    PROCESSING_QUEUE_URL = module.sqs_processing.queue_url
    ALERTS_TABLE         = module.dynamodb_alerts.table_name
  }

  tags = local.common_tags
}

# Lambda Function URL for demo/testing - allows direct invocation from web page
resource "aws_lambda_function_url" "ingestor_demo" {
  function_name      = module.lambda_ingestor.function_name
  authorization_type = "NONE" # Public access for demo

  cors {
    allow_origins     = ["*"]
    allow_methods     = ["POST", "OPTIONS"]
    allow_headers     = ["content-type", "x-amz-date", "authorization", "x-api-key"]
    expose_headers    = ["x-amz-request-id"]
    max_age           = 86400
    allow_credentials = false
  }
}

module "lambda_analyzer" {
  source = "./modules/lambda"

  function_name = "${local.name_prefix}-analyzer"
  description   = "Analyzes alerts using AI (${var.ai_provider == "anthropic" ? "Claude" : "Gemini"})"
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime

  source_dir = "${local.lambda_source_dir}/analyzer"

  role_arn = module.iam_analyzer.role_arn

  memory_size = var.analyzer_memory_size
  timeout     = var.analyzer_timeout

  environment_variables = merge(
    {
      ENVIRONMENT            = var.environment
      AI_PROVIDER            = var.ai_provider
      ALERTS_TABLE           = module.dynamodb_alerts.table_name
      ANALYSIS_CACHE_TABLE   = module.dynamodb_cache.table_name
      DISTRIBUTION_QUEUE_URL = module.sqs_distribution.queue_url
    },
    var.ai_provider == "anthropic" ? {
      ANTHROPIC_API_KEY_PARAM = aws_ssm_parameter.anthropic_api_key[0].name
    } : {},
    var.ai_provider == "google" ? {
      GOOGLE_API_KEY_PARAM = aws_ssm_parameter.google_api_key[0].name
    } : {}
  )

  reserved_concurrent_executions = 10 # Limit concurrency to control Claude API costs

  tags = local.common_tags
}

module "lambda_slack_notifier" {
  source = "./modules/lambda"

  function_name = "${local.name_prefix}-slack-notifier"
  description   = "Sends formatted alerts to Slack"
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime

  source_dir = "${local.lambda_source_dir}/slack_notifier"

  role_arn = module.iam_notifier.role_arn

  memory_size = var.notifier_memory_size
  timeout     = var.notifier_timeout

  environment_variables = {
    ENVIRONMENT            = var.environment
    ALERTS_TABLE           = module.dynamodb_alerts.table_name
    SLACK_BOT_TOKEN_SECRET = data.aws_secretsmanager_secret.slack_bot_token.name
    SLACK_CHANNEL          = var.slack_channel
  }

  tags = local.common_tags
}

# Jira Notifier Lambda (only created if Jira is enabled)
module "lambda_jira_notifier" {
  count  = var.jira_enabled ? 1 : 0
  source = "./modules/lambda"

  function_name = "${local.name_prefix}-jira-notifier"
  description   = "Creates Jira tickets for alerts"
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime

  source_dir = "${local.lambda_source_dir}/jira_notifier"

  role_arn = module.iam_notifier.role_arn

  memory_size = var.notifier_memory_size
  timeout     = var.notifier_timeout

  environment_variables = {
    ENVIRONMENT         = var.environment
    ALERTS_TABLE        = module.dynamodb_alerts.table_name
    JIRA_URL            = var.jira_url
    JIRA_PROJECT_KEY    = var.jira_project_key
    JIRA_ISSUE_TYPE     = var.jira_issue_type
    JIRA_API_TOKEN_PARAM = var.jira_enabled ? aws_ssm_parameter.jira_api_token[0].name : ""
  }

  tags = local.common_tags
}

# Slack Interactions Handler Lambda (handles button clicks)
module "lambda_slack_interactions" {
  source = "./modules/lambda"

  function_name = "${local.name_prefix}-slack-interactions"
  description   = "Handles Slack interactive button clicks"
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime

  source_dir = "${local.lambda_source_dir}/slack_interactions"

  role_arn = module.iam_notifier.role_arn

  memory_size = 512
  timeout     = 30

  environment_variables = {
    ENVIRONMENT           = var.environment
    ALERTS_TABLE          = module.dynamodb_alerts.table_name
    JIRA_QUEUE_URL        = var.jira_enabled ? module.sqs_jira[0].queue_url : ""
    SLACK_SIGNING_SECRET  = var.slack_signing_secret_name
  }

  tags = local.common_tags
}

# Lambda Event Source Mappings
resource "aws_lambda_event_source_mapping" "analyzer_sqs" {
  event_source_arn = module.sqs_processing.queue_arn
  function_name    = module.lambda_analyzer.function_arn
  batch_size       = 1
  enabled          = true

  scaling_config {
    maximum_concurrency = 10
  }
}

resource "aws_lambda_event_source_mapping" "notifier_sqs" {
  event_source_arn = module.sqs_distribution.queue_arn
  function_name    = module.lambda_slack_notifier.function_arn
  batch_size       = 1
  enabled          = true
}

resource "aws_lambda_event_source_mapping" "jira_notifier_sqs" {
  count            = var.jira_enabled ? 1 : 0
  event_source_arn = module.sqs_jira[0].queue_arn
  function_name    = module.lambda_jira_notifier[0].function_arn
  batch_size       = 1
  enabled          = true
}

# EventBridge Rule for CloudWatch Events
module "eventbridge" {
  source = "./modules/eventbridge"

  rule_name        = "${local.name_prefix}-cloudwatch-alerts"
  rule_description = "Routes CloudWatch error and warning events to ingestor"
  rule_state       = var.eventbridge_rule_state

  event_pattern = jsonencode({
    source      = ["aws.logs"]
    detail-type = ["CloudWatch Logs"]
    detail = {
      logGroup = var.cloudwatch_log_group_patterns
      logLevel = ["ERROR", "WARN", "CRITICAL"]
    }
  })

  target_arn = module.lambda_ingestor.function_arn

  tags = local.common_tags
}

# Grant EventBridge permission to invoke Lambda
resource "aws_lambda_permission" "eventbridge_invoke_ingestor" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ingestor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = module.eventbridge.rule_arn
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "processing_dlq_alarm" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-processing-dlq-alarm"
  alarm_description   = "Alert when messages arrive in processing DLQ"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = var.dlq_alarm_threshold

  dimensions = {
    QueueName = module.sqs_processing.dlq_name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "distribution_dlq_alarm" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-distribution-dlq-alarm"
  alarm_description   = "Alert when messages arrive in distribution DLQ"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = var.dlq_alarm_threshold

  dimensions = {
    QueueName = module.sqs_distribution.dlq_name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "analyzer_errors" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-analyzer-errors"
  alarm_description   = "Alert when analyzer Lambda error rate is high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = var.lambda_error_rate_threshold

  dimensions = {
    FunctionName = module.lambda_analyzer.function_name
  }

  tags = local.common_tags
}

# API Gateway for Slack Interactions
resource "aws_apigatewayv2_api" "slack_interactions" {
  name          = "${local.name_prefix}-slack-interactions"
  protocol_type = "HTTP"
  description   = "API Gateway for handling Slack interactive button clicks"

  tags = local.common_tags
}

resource "aws_apigatewayv2_stage" "slack_interactions" {
  api_id      = aws_apigatewayv2_api.slack_interactions.id
  name        = var.environment
  auto_deploy = true

  tags = local.common_tags
}

resource "aws_apigatewayv2_integration" "slack_interactions" {
  api_id                 = aws_apigatewayv2_api.slack_interactions.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.lambda_slack_interactions.function_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "slack_interactions" {
  api_id    = aws_apigatewayv2_api.slack_interactions.id
  route_key = "POST /slack/interactions"
  target    = "integrations/${aws_apigatewayv2_integration.slack_interactions.id}"
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_slack_interactions.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.slack_interactions.execution_arn}/*/*"
}