# Profile "scalable" on AWS: ECS on EC2 (Graviton on-demand base + Spot), ALB, SQS + dead-letter queues,
# S3 for files, EventBridge Scheduler for the 5-minute tick. Neon stays the database (pooled URL).
#
#   cd deploy/aws && terraform init && terraform apply -var-file=prod.tfvars
#
# Cost notes: no NAT gateway (instances sit in public subnets and only accept traffic from the ALB);
# Spot capacity can drop to zero; one small on-demand instance is the floor.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.80" }
  }
  # Keep state in S3 for a team (create the bucket once, then uncomment):
  # backend "s3" { bucket = "lms-terraform-state" key = "prod/terraform.tfstate" region = "ap-southeast-1" }
}

provider "aws" {
  region = var.region
  default_tags { tags = { app = var.name, managed_by = "terraform" } }
}

data "aws_availability_zones" "available" { state = "available" }
data "aws_caller_identity" "me" {}

locals {
  azs    = slice(data.aws_availability_zones.available.names, 0, 2)
  queues = ["notifications", "authoring", "reports", "scheduled"]
  # Plain settings for every container (secrets come from Secrets Manager, see iam.tf / services.tf).
  app_env = {
    LMS_DEPLOY_PROFILE     = "scalable"
    LMS_ENVIRONMENT        = "production"
    LMS_AWS_REGION         = var.region
    LMS_SQS_QUEUE_PREFIX   = "${var.name}-"
    LMS_SQS_CREATE_QUEUES  = "false" # queues are created here
    LMS_S3_BUCKET          = aws_s3_bucket.files.bucket
    LMS_SCHEDULER_SOURCE   = "external"
    LMS_SCHEDULER_ENABLED  = "false"
    LMS_CORS_ORIGINS       = var.public_url
    LMS_PUBLIC_APP_URL     = var.public_url
    LMS_AI_PROVIDER        = var.ai_provider
    LMS_SEED_DEMO_DATA     = "false"
    LMS_WORKER_CONCURRENCY = tostring(var.worker_concurrency)
    LMS_TIMEZONE           = var.timezone
    RUN_MIGRATIONS         = "false" # the deploy workflow runs one migration task first
  }
}

# ---- network: 2 public subnets, no NAT --------------------------------------------------------
resource "aws_vpc" "main" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}

resource "aws_internet_gateway" "main" { vpc_id = aws_vpc.main.id }

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "alb" {
  name   = "${var.name}-alb"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "instances" {
  name   = "${var.name}-ecs-instances"
  vpc_id = aws_vpc.main.id
  # Bridge networking uses dynamic host ports; only the ALB may reach them.
  ingress {
    from_port       = 32768
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress { # Neon, SQS, S3, Groq, ECR
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Free gateway endpoint: S3 traffic stays inside AWS.
resource "aws_vpc_endpoint" "s3" {
  vpc_id          = aws_vpc.main.id
  service_name    = "com.amazonaws.${var.region}.s3"
  route_table_ids = [aws_route_table.public.id]
}
