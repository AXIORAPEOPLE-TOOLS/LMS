# ---- SQS: one queue + one dead-letter queue per logical queue ------------------------------------
resource "aws_sqs_queue" "dlq" {
  for_each                  = toset(local.queues)
  name                      = "${var.name}-${each.key}-dlq"
  message_retention_seconds = 1209600 # 14 days to look at and replay failures
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "jobs" {
  for_each                   = toset(local.queues)
  name                       = "${var.name}-${each.key}"
  visibility_timeout_seconds = 300 # the worker extends it for long jobs
  receive_wait_time_seconds  = 20  # long polling: fewer empty receives, lower cost
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 5 # = LMS_JOB_ATTEMPTS
  })
}

# ---- S3: knowledge attachments and proctoring pictures ---------------------------------------
resource "aws_s3_bucket" "files" {
  bucket_prefix = "${var.name}-files-"
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_versioning" "files" {
  bucket = aws_s3_bucket.files.id
  versioning_configuration { status = "Enabled" } # an overwritten or deleted file can be recovered
}

resource "aws_s3_bucket_lifecycle_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    id     = "old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

# ---- EventBridge Scheduler: the 5-minute tick -> scheduled queue -> any worker ------------------
resource "aws_scheduler_schedule" "tick" {
  name                = "${var.name}-scheduler-tick"
  schedule_expression = "rate(5 minutes)"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_sqs_queue.jobs["scheduled"].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ name = "scheduler.run", data = {} })
  }
}

# ---- alarms --------------------------------------------------------------------------------------
resource "aws_sns_topic" "alarms" { name = "${var.name}-alarms" }

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "dead_letters" {
  for_each            = toset(local.queues)
  alarm_name          = "${var.name}-${each.key}-dead-letters"
  alarm_description   = "Jobs on ${each.key} failed 5 times. Look at the worker log, fix, then redrive from the console."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq[each.key].name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name}-api-5xx"
  alarm_description   = "The API returned server errors."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}
