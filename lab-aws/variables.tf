variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-2"
  
  # Common regions and their characteristics:
  # us-east-2 (Ohio) - Default, good pricing, reliable
  # us-east-1 (N. Virginia) - Lowest prices, all services available
  # us-west-2 (Oregon) - Good for West Coast, reliable
  # eu-west-1 (Ireland) - Good for Europe
  # ap-southeast-1 (Singapore) - Good for Asia
  #
  # Note: Spot prices vary by region. Check pricing before choosing.
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
  default     = "containerlab"
}

variable "ssh_key_name" {
  description = "Name of existing AWS SSH key pair"
  type        = string
}

variable "admin_ip" {
  description = "Your public IP address for SSH access (CIDR notation)"
  type        = string
  # Example: "203.0.113.0/32"
}

variable "vpn_instance_type" {
  description = "EC2 instance type for VPN server (on-demand only for reliability)"
  type        = string
  default     = "t3.micro"
  
  # VPN server is always on-demand for reliability
  # Options:
  # "t3.micro"  - $0.0104/hr, 1 GB RAM, 2 vCPU (recommended)
  # "t3.small"  - $0.0208/hr, 2 GB RAM, 2 vCPU (if you need more resources)
  # "t3.nano"   - $0.0052/hr, 0.5 GB RAM, 2 vCPU (minimal, may be too small)
}

variable "lab_instance_type" {
  description = "EC2 instance type for lab server"
  type        = string
  default     = "r6i.xlarge"
  
  # Memory-optimized instances for containerlab (uses spot pricing):
  # "r7i.xlarge"    - 32 GB RAM, 4 vCPU   (good for 10-15 cEOS nodes)
  # "r7i.2xlarge"   - 64 GB RAM, 8 vCPU   (good for 20-30 cEOS nodes)
  # "r7iz.2xlarge"  - 64 GB RAM, 8 vCPU   (higher CPU freq, best performance)
  # "r6i.xlarge"    - 32 GB RAM, 4 vCPU   (previous gen, cheaper)
  # "r6i.2xlarge"   - 64 GB RAM, 8 vCPU   (previous gen)
  # "r5.xlarge"     - 32 GB RAM, 4 vCPU   (older gen, even cheaper)
  # "r5.2xlarge"    - 64 GB RAM, 8 vCPU   (older gen)
  #
  # Compute-optimized alternatives (less RAM, better CPU):
  # "c6i.2xlarge"   - 16 GB RAM, 8 vCPU   (if CPU-bound workloads)
  # "c7i.2xlarge"   - 16 GB RAM, 8 vCPU   (latest gen)
  #
  # General purpose alternatives:
  # "m6i.xlarge"    - 16 GB RAM, 4 vCPU   (balanced)
  # "m6i.2xlarge"   - 32 GB RAM, 8 vCPU   (balanced)
}

variable "spot_max_price" {
  description = "Maximum spot price for LAB SERVER (leave empty for on-demand price). VPN server always uses on-demand for reliability."
  type        = string
  default     = ""  # Empty means on-demand price
  
  # Example spot prices (as of 2024, varies by region):
  # r7i.xlarge spot: ~$0.08-0.12/hr vs on-demand $0.2688/hr (60-70% savings)
  # r7i.2xlarge spot: ~$0.16-0.24/hr vs on-demand $0.5376/hr (60-70% savings)
  #
  # NOTE: Only the LAB SERVER uses spot instances. The VPN server uses on-demand
  # for reliability since losing VPN access breaks all connectivity.
  #
  # To force on-demand for lab server (not recommended), set a very high price like "1.00"
}

variable "lab_disk_size" {
  description = "Root disk size in GB for lab server"
  type        = number
  default     = 100
  
  # cEOS images are ~1.5GB each, containerlab needs space for:
  # - Base OS (~10 GB)
  # - Docker images (10-20 GB)
  # - Container storage (20-30 GB)
  # - Logs and working data (20-30 GB)
}

variable "example_topology_url" {
  description = "URL to download example containerlab topology file"
  type        = string
  default     = "https://raw.githubusercontent.com/rbmacd/frey/main/lab-aws/example-topology.yaml"
  
  # This URL is downloaded during lab server setup
  # Change this to use your own topology file
  # Set to empty string ("") to skip downloading example topology
}