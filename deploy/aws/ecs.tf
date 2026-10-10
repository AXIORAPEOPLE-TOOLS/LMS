# ---- image registry --------------------------------------------------------------------------
resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({ rules = [{
    rulePriority = 1, description = "keep the last 20 images"
    selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
    action       = { type = "expire" }
  }] })
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name}"
  retention_in_days = 30
}

# ---- cluster and EC2 capacity ------------------------------------------------------------------
resource "aws_ecs_cluster" "main" {
  name = var.name
}

data "aws_ssm_parameter" "ecs_ami_arm64" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2023/arm64/recommended/image_id"
}

resource "aws_launch_template" "ecs" {
  name_prefix            = "${var.name}-ecs-"
  image_id               = data.aws_ssm_parameter.ecs_ami_arm64.value
  instance_type          = var.base_instance_type
  vpc_security_group_ids = [aws_security_group.instances.id]
  iam_instance_profile { arn = aws_iam_instance_profile.instance.arn }
  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2
  }
  user_data = base64encode(<<-EOT
    #!/bin/bash
    cat >> /etc/ecs/ecs.config <<EOF
    ECS_CLUSTER=${aws_ecs_cluster.main.name}
    ECS_ENABLE_SPOT_INSTANCE_DRAINING=true
    ECS_CONTAINER_STOP_TIMEOUT=120s
    EOF
  EOT
  )
}

# On-demand floor: always one instance, runs the first API and worker tasks.
resource "aws_autoscaling_group" "base" {
  name_prefix           = "${var.name}-base-"
  vpc_zone_identifier   = aws_subnet.public[*].id
  min_size              = 1
  max_size              = 2
  protect_from_scale_in = false
  launch_template {
    id      = aws_launch_template.ecs.id
    version = "$Latest"
  }
  tag {
    key                 = "AmazonECSManaged"
    value               = "true"
    propagate_at_launch = true
  }
  lifecycle { ignore_changes = [desired_capacity] }
}

# Spot pool: scales from zero for bursts (bulk sends, many learners at once).
resource "aws_autoscaling_group" "spot" {
  name_prefix           = "${var.name}-spot-"
  vpc_zone_identifier   = aws_subnet.public[*].id
  min_size              = 0
  max_size              = var.spot_max_instances
  capacity_rebalance    = true
  protect_from_scale_in = false
  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "price-capacity-optimized"
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.ecs.id
        version            = "$Latest"
      }
      dynamic "override" {
        for_each = var.spot_instance_types
        content { instance_type = override.value }
      }
    }
  }
  tag {
    key                 = "AmazonECSManaged"
    value               = "true"
    propagate_at_launch = true
  }
  lifecycle { ignore_changes = [desired_capacity] }
}

resource "aws_ecs_capacity_provider" "base" {
  name = "${var.name}-base"
  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.base.arn
    managed_scaling {
      status          = "ENABLED"
      target_capacity = 100
    }
  }
}

resource "aws_ecs_capacity_provider" "spot" {
  name = "${var.name}-spot"
  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.spot.arn
    managed_scaling {
      status          = "ENABLED"
      target_capacity = 100 # add instances only when tasks do not fit
    }
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = [aws_ecs_capacity_provider.base.name, aws_ecs_capacity_provider.spot.name]
  default_capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.spot.name
    weight            = 1
  }
}

# ---- load balancer -------------------------------------------------------------------------------
resource "aws_lb" "main" {
  name               = var.name
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
  idle_timeout       = 120 # course uploads
}

resource "aws_lb_target_group" "api" {
  name                 = "${var.name}-api"
  port                 = 8000
  protocol             = "HTTP"
  vpc_id               = aws_vpc.main.id
  target_type          = "instance" # bridge networking, dynamic host ports
  deregistration_delay = 30
  health_check {
    path                = "/api/health/live"
    matcher             = "200"
    interval            = 15
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.api.arn
    }
  }
  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [] : [1]
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = var.certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ---- task definitions ------------------------------------------------------------------------
locals {
  image       = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
  environment = [for k, v in local.app_env : { name = k, value = v }]
  secrets = [for key in ["LMS_DATABASE_URL", "LMS_JWT_SECRET", "LMS_GROQ_API_KEY", "LMS_REDIS_URL"] :
    { name = key, valueFrom = "${var.secrets_arn}:${key}::" }
  ]
  logs = { logDriver = "awslogs", options = {
    awslogs-group = aws_cloudwatch_log_group.app.name, awslogs-region = var.region, awslogs-stream-prefix = "app"
  } }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  requires_compatibilities = ["EC2"]
  network_mode             = "bridge"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name              = "api"
    image             = local.image
    essential         = true
    cpu               = 512
    memoryReservation = 768
    memory            = 1536
    portMappings      = [{ containerPort = 8000, hostPort = 0, protocol = "tcp" }]
    environment       = concat(local.environment, [{ name = "WEB_CONCURRENCY", value = "2" }])
    secrets           = local.secrets
    logConfiguration  = local.logs
    stopTimeout       = 30
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name}-worker"
  requires_compatibilities = ["EC2"]
  network_mode             = "bridge"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name              = "worker"
    image             = local.image
    essential         = true
    command           = ["python", "-m", "app.worker"]
    cpu               = 512
    memoryReservation = 768
    memory            = 1536
    environment       = local.environment
    secrets           = local.secrets
    logConfiguration  = local.logs
    stopTimeout       = 120 # finish running jobs on deploy / Spot interruption
  }])
}

# One-off: the deploy workflow runs this before rolling out a new image.
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${var.name}-migrate"
  requires_compatibilities = ["EC2"]
  network_mode             = "bridge"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name             = "migrate"
    image            = local.image
    essential        = true
    command          = ["python", "-m", "app.cli", "migrate"]
    cpu              = 256
    memory           = 512
    environment      = local.environment
    secrets          = local.secrets
    logConfiguration = local.logs
  }])
}

# ---- services ----------------------------------------------------------------------------------
resource "aws_ecs_service" "api" {
  name                               = "api"
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.api.arn
  desired_count                      = var.api_min_tasks
  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true # a broken image rolls back by itself
  }
  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.base.name
    base              = 1 # one API task always on on-demand
    weight            = 1
  }
  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.spot.name
    weight            = 2
  }
  ordered_placement_strategy {
    type  = "spread"
    field = "attribute:ecs.availability-zone"
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  lifecycle { ignore_changes = [desired_count, task_definition] } # autoscaling + deploy workflow own these
  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "worker" {
  name                               = "worker"
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.worker.arn
  desired_count                      = var.worker_min_tasks
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.base.name
    base              = 1 # one worker always on on-demand
    weight            = 0
  }
  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.spot.name
    weight            = 1 # extra workers on Spot
  }
  ordered_placement_strategy {
    type  = "binpack"
    field = "memory"
  }
  lifecycle { ignore_changes = [desired_count, task_definition] }
}

# ---- autoscaling ---------------------------------------------------------------------------------
resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.api_min_tasks
  max_capacity       = var.api_max_tasks
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${var.name}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification { predefined_metric_type = "ECSServiceAverageCPUUtilization" }
  }
}

resource "aws_appautoscaling_policy" "api_requests" {
  name               = "${var.name}-api-requests"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value       = 600 # requests per task per minute
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.main.arn_suffix}/${aws_lb_target_group.api.arn_suffix}"
    }
  }
}

resource "aws_appautoscaling_target" "worker" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.worker_min_tasks
  max_capacity       = var.worker_max_tasks
}

# Workers follow the backlog: total waiting messages across the queues.
resource "aws_appautoscaling_policy" "worker_out" {
  name               = "${var.name}-worker-out"
  policy_type        = "StepScaling"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"
    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = var.backlog_per_worker * 4
      scaling_adjustment          = 1
    }
    step_adjustment {
      metric_interval_lower_bound = var.backlog_per_worker * 4
      metric_interval_upper_bound = var.backlog_per_worker * 20
      scaling_adjustment          = 3
    }
    step_adjustment {
      metric_interval_lower_bound = var.backlog_per_worker * 20
      scaling_adjustment          = 5
    }
  }
}

resource "aws_appautoscaling_policy" "worker_in" {
  name               = "${var.name}-worker-in"
  policy_type        = "StepScaling"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 300
    metric_aggregation_type = "Maximum"
    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = -1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "backlog_high" {
  alarm_name          = "${var.name}-backlog-high"
  alarm_description   = "More waiting jobs than the workers can take: add workers."
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.backlog_per_worker
  evaluation_periods  = 1
  alarm_actions       = [aws_appautoscaling_policy.worker_out.arn]
  dynamic "metric_query" {
    for_each = toset(local.queues)
    content {
      id = "q_${metric_query.key}"
      metric {
        namespace   = "AWS/SQS"
        metric_name = "ApproximateNumberOfMessagesVisible"
        dimensions  = { QueueName = aws_sqs_queue.jobs[metric_query.key].name }
        stat        = "Maximum"
        period      = 60
      }
    }
  }
  metric_query {
    id          = "backlog"
    expression  = join("+", [for q in local.queues : "q_${q}"])
    label       = "Waiting jobs"
    return_data = true
  }
}

resource "aws_cloudwatch_metric_alarm" "backlog_empty" {
  alarm_name          = "${var.name}-backlog-empty"
  alarm_description   = "Queues empty for 10 minutes: remove a worker (down to the minimum)."
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  evaluation_periods  = 10
  alarm_actions       = [aws_appautoscaling_policy.worker_in.arn]
  dynamic "metric_query" {
    for_each = toset(local.queues)
    content {
      id = "q_${metric_query.key}"
      metric {
        namespace   = "AWS/SQS"
        metric_name = "ApproximateNumberOfMessagesVisible"
        dimensions  = { QueueName = aws_sqs_queue.jobs[metric_query.key].name }
        stat        = "Maximum"
        period      = 60
      }
    }
  }
  metric_query {
    id          = "backlog"
    expression  = join("+", [for q in local.queues : "q_${q}"])
    label       = "Waiting jobs"
    return_data = true
  }
}

# ---- outputs ---------------------------------------------------------------------------------
output "load_balancer_dns" { value = aws_lb.main.dns_name }
output "ecr_repository" { value = aws_ecr_repository.app.repository_url }
output "files_bucket" { value = aws_s3_bucket.files.bucket }
output "cluster" { value = aws_ecs_cluster.main.name }
output "subnets" { value = aws_subnet.public[*].id }
output "instance_security_group" { value = aws_security_group.instances.id }
