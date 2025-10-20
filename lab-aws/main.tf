terraform {
  required_version = ">= 1.0"
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

# VPC
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

# Single Public Subnet (for both VPN and Lab Server)
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet"
  }
}

# Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

# Route Table Association
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Elastic IP for VPN Server
resource "aws_eip" "vpn" {
  domain   = "vpc"
  instance = aws_instance.vpn.id

  tags = {
    Name = "${var.project_name}-vpn-eip"
  }
}

# Security Group for VPN Server
resource "aws_security_group" "vpn" {
  name_prefix = "${var.project_name}-vpn-"
  description = "Security group for WireGuard VPN server"
  vpc_id      = aws_vpc.main.id

  # WireGuard
  ingress {
    from_port   = 51820
    to_port     = 51820
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "WireGuard VPN"
  }

  # SSH from admin IP only
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_ip]
    description = "SSH access"
  }

  # Allow all outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-vpn-sg"
  }
}

# Security Group for Lab Server
resource "aws_security_group" "lab" {
  name_prefix = "${var.project_name}-lab-"
  description = "Security group for lab server - VPN access only"
  vpc_id      = aws_vpc.main.id

  # SSH from VPN server only
  ingress {
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.vpn.id]
    description     = "SSH from VPN server"
  }

  # Allow all traffic from VPN clients
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.13.13.0/24"]
    description = "All traffic from VPN clients"
  }

  # Allow all outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-lab-sg"
  }
}

# Data source for latest Ubuntu AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# VPN Server (WireGuard) - On-Demand Instance
# Uses on-demand pricing for guaranteed availability
# Cost: ~$0.01/hr - critical for reliable VPN access
resource "aws_instance" "vpn" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.vpn_instance_type
  subnet_id     = aws_subnet.public.id

  vpc_security_group_ids = [aws_security_group.vpn.id]
  key_name               = var.ssh_key_name

  user_data = templatefile("${path.module}/wireguard-setup.sh", {
    vpn_subnet     = "10.13.13.0/24"
    lab_server_ip  = "10.0.1.100"
  })

  tags = {
    Name = "${var.project_name}-vpn-server"
  }
}

# Lab Server - Spot Instance for Cost Optimization
# Uses spot pricing for 60-70% cost savings
# Interruptions are rare (<5%) and acceptable for ephemeral testing
# If interrupted, simply run 'terraform apply' again
resource "aws_spot_instance_request" "lab" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.lab_instance_type
  subnet_id     = aws_subnet.public.id

  vpc_security_group_ids = [aws_security_group.lab.id]
  key_name               = var.ssh_key_name

  # Request a specific private IP for easier VPN routing
  private_ip = "10.0.1.100"

  spot_price           = var.spot_max_price
  wait_for_fulfillment = true
  spot_type            = "one-time"

  root_block_device {
    volume_size           = var.lab_disk_size
    volume_type           = "gp3"
    iops                  = 3000
    throughput            = 125
    delete_on_termination = true
  }

  user_data = file("${path.module}/lab-setup.sh")

  tags = {
    Name = "${var.project_name}-lab-server"
  }
}

# Tag the spot instance after creation
resource "aws_ec2_tag" "lab_instance" {
  resource_id = aws_spot_instance_request.lab.spot_instance_id
  key         = "Name"
  value       = "${var.project_name}-lab-server"
}