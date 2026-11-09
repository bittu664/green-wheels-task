terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "logs_kms_key_arn" {
  description = "Optional regional customer-managed key with CloudWatch Logs permissions."
  type        = string
  default     = null
}

locals {
  name = "greenwheels-lease-${var.environment}"
  signals = {
    Ingestion5xx = {
      pattern     = "{ ($.kind = \"http_request\") && ($.route = \"/leases/events\") && ($.method = \"POST\") && ($.status_code >= 500) }"
      threshold   = 5
      description = "Check ingestion failures, recent releases, and database connectivity."
    }
    DatabasePoolTimeout = {
      pattern     = "{ $.kind = \"db_pool_timeout\" }"
      threshold   = 3
      description = "Inspect application pool settings and RDS active connections."
    }
  }
}

resource "aws_cloudwatch_log_group" "lease" {
  name              = "/ecs/${local.name}"
  retention_in_days = 30
  kms_key_id        = var.logs_kms_key_arn
}

resource "aws_sns_topic" "operations" {
  name = local.name
}

resource "aws_cloudwatch_log_metric_filter" "signal" {
  for_each       = local.signals
  name           = each.key
  log_group_name = aws_cloudwatch_log_group.lease.name
  pattern        = each.value.pattern

  metric_transformation {
    namespace     = local.name
    name          = each.key
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "signal" {
  for_each            = aws_cloudwatch_log_metric_filter.signal
  alarm_name          = "${local.name}-${each.key}"
  alarm_description   = local.signals[each.key].description
  namespace           = local.name
  metric_name         = each.key
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  threshold           = local.signals[each.key].threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.operations.arn]
  ok_actions          = [aws_sns_topic.operations.arn]
}

output "log_group" {
  value = aws_cloudwatch_log_group.lease.name
}

output "operations_topic_arn" {
  value = aws_sns_topic.operations.arn
}
