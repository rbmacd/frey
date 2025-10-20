# Containerlab AWS Infrastructure

Terraform infrastructure for deploying ephemeral containerlab environments on AWS with VPN access.

## Quick Summary

**What you get:** A cost-optimized, secure lab environment for network simulations with Arista cEOS and containerlab.

**Cost:** ~$0.10-0.14/hr (~$0.64 for 4-hour session) with default instance types

**Instance Strategy:**
- 🔒 **VPN Server**: On-demand (default: t3.micro, $0.01/hr) - reliable access, always available
- 💰 **Lab Server**: Spot (default: r7i.xlarge, $0.08-0.12/hr) - 60-70% savings, <5% interruption rate
- 🌐 **Direct cEOS Access**: VPN routes 172.20.0.0/16 directly to containerlab networks
- ⚙️ **Fully Configurable**: Both instance types customizable via `terraform.tfvars`

**Deploy time:** ~5 minutes | **Teardown:** ~2 minutes

## Architecture

```
Internet → [IGW] → Public Subnet (10.0.1.0/24)
                    ├─ VPN Server (WireGuard, configurable, default: t3.micro)
                    └─ Lab Server (configurable, default: r7i.xlarge spot)
                         └─ Docker Networks
                              └─ Containerlab (172.20.0.0/16)
                                   ├─ spine1: 172.20.20.2
                                   ├─ spine2: 172.20.20.3
                                   ├─ leaf1: 172.20.20.4
                                   └─ leaf2: 172.20.20.5

VPN Client (10.13.13.2) ──[VPN tunnel]──> VPN Server
                                              │
                                              ├──> Lab Server (10.0.1.100)
                                              └──> cEOS instances (172.20.x.x) ✓
```

**Network Flow:**
1. VPN client connects to VPN server (10.13.13.2 → VPN server)
2. VPN server routes to lab server (10.0.1.100)
3. Lab server routes to containerlab networks (172.20.0.0/16)
4. **Result**: VPN clients have direct IP access to all cEOS instances!

**Design Highlights:**
- **Simplified**: Single subnet, no NAT instance needed
- **Secure**: Lab server only accessible via VPN (security groups enforce this)
- **Direct cEOS Access**: VPN clients can reach containerlab management IPs directly
- **Cost-Optimized**: WireGuard VPN instead of AWS Client VPN saves $0.45/hr
- **Fully Configurable**: Both VPN and Lab instance types are variables
- **Hybrid Instance Strategy**: 
  - VPN Server: On-demand (default: t3.micro) for reliability
  - Lab Server: Spot (default: r7i.xlarge) for 60-70% savings
- **Fast**: Deploy/destroy in ~5 minutes
- GP3 EBS storage optimized for IOPS

## Instance Strategy Explained

This infrastructure uses a **hybrid approach** to balance cost and reliability:

**VPN Server (default: t3.micro - On-Demand)**
- Default cost: $0.0104/hr (~$7.50/month if left running)
- Configurable via `vpn_instance_type` in terraform.tfvars
- **Why on-demand?** The VPN server is your gateway to everything. If it's interrupted, you lose all access to your lab environment. The small cost ($0.01/hr with default) is worth the guaranteed availability.
- Always available, no interruptions
- Hosts WireGuard VPN for secure access

**Lab Server (default: r7i.xlarge - Spot)**
- Default cost: $0.08-0.12/hr spot vs $0.27/hr on-demand (60-70% savings)
- Configurable via `lab_instance_type` in terraform.tfvars
- **Why spot?** This is where the real compute costs are. Spot pricing on r-family instances saves $100-150/month if running continuously.
- Interruption rate: <5% (very rare for r-family memory-optimized instances)
- If interrupted: Simply run `terraform apply` again to get a new instance
- Perfect for ephemeral testing - you're destroying it after each session anyway

**The Math (using defaults):**
- Spot savings on lab server: ~$0.16/hr
- VPN on-demand cost: $0.01/hr
- **Net savings: ~$0.15/hr (93% of spot savings retained)**

**Customization:**
You can easily change either instance type:
```hcl
# terraform.tfvars
vpn_instance_type = "t3.small"     # If you need more VPN resources
lab_instance_type = "r7i.2xlarge"  # For larger topologies
```

## Cost Breakdown

### Hourly Costs (US-East-1)

**Note:** Costs shown are examples using default instance types. Adjust based on your `vpn_instance_type` and `lab_instance_type` selections.

| Resource | Default Type | Instance Mode | Cost/Hr | Notes |
|----------|--------------|---------------|---------|-------|
| **VPN Server** | t3.micro | **On-Demand** | **$0.0104** | Configurable via `vpn_instance_type` |
| **Lab Server** | r7i.xlarge | **Spot** | **$0.08-0.12** | Configurable via `lab_instance_type` |
| Lab Server | r7i.xlarge | On-Demand | $0.2688 | Not recommended |
| Lab Server | r7i.2xlarge | Spot | $0.16-0.24 | 64 GB RAM option |
| Lab Server | r7i.2xlarge | On-Demand | $0.5376 | Not recommended |
| Lab Server | r7iz.2xlarge | Spot | $0.19-0.28 | Highest performance |
| EBS Storage | gp3 100GB | N/A | $0.0114 | $8/month |
| Elastic IP | 1 IP | N/A | $0.0025 | $1.80/month |
| **TOTAL (defaults)** | | **Mixed** | **$0.10-0.14/hr** | **Using r7i.xlarge spot + t3.micro** |

**Instance Strategy:**
- **VPN Server**: On-demand for stable VPN access (interruptions = no connectivity)
- **Lab Server**: Spot for maximum cost savings (interruptions rare and acceptable)
- **Both are configurable** via terraform.tfvars

### Cost Scenarios

**Using Default Instance Types (t3.micro VPN + r7i.xlarge spot Lab):**

**4-Hour Testing Session:**
- VPN Server (t3.micro on-demand): 4 hrs × $0.0104 = $0.04
- Lab Server (r7i.xlarge spot): 4 hrs × $0.11 = $0.44
- Storage + IP: 4 hrs × $0.0139 = $0.06
- Data transfer: ~$0.10
- **Total: ~$0.64**

**8-Hour Work Day:**
- VPN Server (t3.micro on-demand): 8 hrs × $0.0104 = $0.08
- Lab Server (r7i.xlarge spot): 8 hrs × $0.11 = $0.88
- Storage + IP: 8 hrs × $0.0139 = $0.11
- Data transfer: ~$0.20
- **Total: ~$1.27**

**Using Larger Lab Server (t3.micro VPN + r7i.2xlarge spot Lab):**

**8-Hour Work Day:**
- VPN Server: 8 hrs × $0.0104 = $0.08
- Lab Server (r7i.2xlarge spot): 8 hrs × $0.20 = $1.60
- Storage + IP: 8 hrs × $0.0139 = $0.11
- Data transfer: ~$0.20
- **Total: ~$1.99**

**Full Month - NOT Recommended (on-demand instances):**
- VPN Server (t3.micro): 730 hrs × $0.0104 = $8
- Lab Server (r7i.xlarge on-demand): 730 hrs × $0.2688 = $196
- Storage + IP: $10
- **Total: ~$214/month**
- **Better approach**: Deploy only when needed with spot instances

### Cost Optimization Tips

1. **Lab Server Uses Spot Instances**: 60-70% savings with very rare interruptions for r-family instances. If interrupted, simply redeploy.
2. **VPN Server Uses On-Demand**: Small cost ($0.01/hr) ensures reliable access. Never use spot for VPN as interruptions break connectivity.
3. **Deploy Only When Needed**: Full setup takes ~5 min, teardown takes ~2 min
4. **Choose Right Size**: Start with r7i.xlarge, scale up if needed
5. **Monitor Spend**: Set AWS Budget alerts at $10, $25, $50
6. **Destroy When Done**: `terraform destroy` removes ALL resources
7. **Single Subnet Design**: Eliminates NAT costs entirely

### Regional Pricing Differences

Spot prices vary by region. Here are typical spot prices for r7i.xlarge:
- us-east-1 (N. Virginia): $0.08-0.12/hr
- us-west-2 (Oregon): $0.09-0.13/hr  
- eu-west-1 (Ireland): $0.10-0.14/hr
- ap-southeast-1 (Singapore): $0.12-0.16/hr

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Terraform** installed (v1.0+)
3. **AWS CLI** configured with credentials
4. **SSH Key Pair** created in AWS Console
5. **WireGuard Client** for VPN access

## Quick Start

### 1. Clone and Configure

```bash
# Create project directory
mkdir containerlab-infra && cd containerlab-infra

# Copy all Terraform files into this directory
# (main.tf, variables.tf, outputs.tf, *.sh)

# Create configuration file
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars
```

**Key configuration options in terraform.tfvars:**
- `ssh_key_name` - Your AWS SSH key pair name
- `admin_ip` - Your public IP in CIDR format (e.g., "1.2.3.4/32")
- `vpn_instance_type` - VPN server size (default: t3.micro)
- `lab_instance_type` - Lab server size (default: r7i.xlarge)
- `spot_max_price` - Max spot price for lab server (leave empty for on-demand price)
- `lab_disk_size` - Disk size in GB (default: 100)

### 2. Get Your Public IP

```bash
# Linux/Mac
curl ifconfig.me

# Add /32 to the end for CIDR notation
# Example: 203.0.113.45/32
```

### 3. Create AWS SSH Key Pair

```bash
# Via AWS Console:
# EC2 > Key Pairs > Create Key Pair > Save .pem file

# Or via CLI:
aws ec2 create-key-pair --key-name containerlab-key \
  --query 'KeyMaterial' --output text > containerlab-key.pem
chmod 400 containerlab-key.pem
```

### 4. Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Review planned changes
terraform plan

# Deploy (takes ~5 minutes)
terraform apply

# Save outputs
terraform output > connection-info.txt
```

### 5. Connect to VPN

```bash
# SSH to VPN server
ssh -i containerlab-key.pem ubuntu@<VPN_SERVER_IP>

# Retrieve WireGuard client config
cat ~/client1.conf

# Copy the entire config output
# Exit SSH
exit
```

### 6. Setup WireGuard Client

**Mac/Linux:**
```bash
# Save config
vim ~/wireguard-containerlab.conf
# Paste the config from previous step

# Install WireGuard
# Mac: brew install wireguard-tools
# Ubuntu: apt install wireguard

# Connect
sudo wg-quick up ~/wireguard-containerlab.conf
```

**Windows:**
1. Download WireGuard: https://www.wireguard.com/install/
2. Open WireGuard app
3. Add Tunnel → Import from file
4. Activate tunnel

### 7. Access Lab Server

```bash
# Once VPN is connected
ssh -i containerlab-key.pem ubuntu@<LAB_SERVER_PRIVATE_IP>

# Read the setup instructions
cat ~/README.txt
```

### 8. Test Direct Access to Containerlab Networks

```bash
# From your laptop (VPN connected), verify routing
ip route | grep 172.20
# Should show: 172.20.0.0/16 via WireGuard interface

# Deploy a test topology on lab server
ssh ubuntu@<LAB_SERVER_IP>
cd ~/containerlab-labs
sudo containerlab deploy -t example-topology.yaml

# Back on your laptop, ping a cEOS instance directly!
ping 172.20.20.2

# SSH directly to cEOS
ssh admin@172.20.20.2
# Password: admin
```

**🎉 You now have direct IP access to all containerlab networks!**

## Using Containerlab

### Network Access Overview

**Your VPN client has direct access to:**
- Lab Server: `10.0.1.100`
- All containerlab management networks: `172.20.0.0/16`
- Individual cEOS instances at their management IPs

This means you can interact with cEOS devices directly from your laptop without SSH tunneling!

### Import Arista cEOS Image

```bash
# On your local machine:
# 1. Download cEOS image from Arista.com (free account required)
# 2. Transfer to lab server
scp cEOS64-lab-4.XX.X.tar.xz ubuntu@<LAB_SERVER_IP>:~/

# On lab server:
docker import cEOS64-lab-4.XX.X.tar.xz ceos:latest
```

### Deploy Example Topology

```bash
cd ~/containerlab-labs

# Review example topology
cat example-topology.yaml

# Deploy
sudo containerlab deploy -t example-topology.yaml

# Check status
sudo containerlab inspect --all
```

**Output will show management IPs:**
```
+---+----------------+-------------+-------------------+-------+
| # |      Name      |    Kind     |   Mgmt IPv4       | State |
+---+----------------+-------------+-------------------+-------+
| 1 | arista-spine1  | ceos        | 172.20.20.2/24    | Up    |
| 2 | arista-spine2  | ceos        | 172.20.20.3/24    | Up    |
| 3 | arista-leaf1   | ceos        | 172.20.20.4/24    | Up    |
| 4 | arista-leaf2   | ceos        | 172.20.20.5/24    | Up    |
+---+----------------+-------------+-------------------+-------+
```

### Access cEOS Instances Directly

**From your laptop** (with VPN connected):

```bash
# SSH directly to any cEOS instance
ssh admin@172.20.20.2
# Default password: admin

# Or use specific devices
ssh admin@172.20.20.3  # spine2
ssh admin@172.20.20.4  # leaf1

# Ping devices
ping 172.20.20.2

# Traceroute through your network
traceroute 172.20.20.5

# Connect with network tools
telnet 172.20.20.2

# Use Ansible against management IPs
ansible-playbook -i '172.20.20.2,172.20.20.3,' playbook.yml
```

**No SSH tunneling needed!** The VPN routes containerlab traffic directly.

### Using Network Management Tools

```bash
# From your laptop with VPN connected:

# Run NAPALM scripts
python my_napalm_script.py --host 172.20.20.2

# Use Nornir
nornir-scrapli show_version --hosts 172.20.20.2,172.20.20.3

# Connect network monitoring tools
# Point Prometheus, Grafana, or other tools to 172.20.x.x IPs

# Use REST APIs if enabled
curl http://172.20.20.2/api/v1/interfaces
```

### Create Custom Topology

```yaml
# ~/containerlab-labs/my-topology.yaml
name: my-network

topology:
  nodes:
    router1:
      kind: ceos
      image: ceos:latest
      mgmt-ipv4: 172.20.20.10
    router2:
      kind: ceos  
      image: ceos:latest
      mgmt-ipv4: 172.20.20.11

  links:
    - endpoints: ["router1:eth1", "router2:eth1"]

# Important: Management network must be in 172.20.0.0/16 range
# This range is automatically routed through the VPN
mgmt:
  network: custom-mgmt
  ipv4-subnet: 172.20.20.0/24
```

**Network Planning:**
- Default containerlab management: `172.20.20.0/24`
- VPN routes entire `172.20.0.0/16` range
- You can use multiple /24 subnets within this range
- Example: `172.20.21.0/24`, `172.20.22.0/24`, etc.

**For larger topologies:**
```yaml
# Different management subnets for different labs
mgmt:
  network: datacenter-lab
  ipv4-subnet: 172.20.30.0/24  # Still within routed range
```

### Cleanup Topology

```bash
# Destroy specific topology
sudo containerlab destroy -t my-topology.yaml

# Destroy all labs
sudo containerlab destroy --all
```

## Teardown

### Destroy Infrastructure

```bash
# Remove all AWS resources
terraform destroy

# Confirm by typing: yes

# Verify nothing remains
terraform show
```

### Disconnect VPN

```bash
# Linux/Mac
sudo wg-quick down ~/wireguard-containerlab.conf

# Windows: Deactivate in WireGuard app
```

## Troubleshooting

### Lab Server Spot Instance Interruption

Spot instances can be interrupted by AWS when capacity is needed (rare for r-family instances). If this happens:

```bash
# Check if spot instance was interrupted
aws ec2 describe-spot-instance-requests \
  --filters Name=state,Values=closed

# Simply redeploy - Terraform will request a new spot instance
terraform apply

# Or use on-demand if you need guaranteed availability
# Edit terraform.tfvars:
# spot_max_price = ""  # Empty means on-demand
```

**Spot Interruption Rates** (historical data):
- r7i.xlarge: <5% interruption rate
- r7i.2xlarge: <3% interruption rate
- If interrupted, you get a 2-minute warning to save work

### Spot Instance Not Launching

```bash
# Check spot price history
aws ec2 describe-spot-price-history \
  --instance-types r7i.xlarge \
  --start-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --product-descriptions "Linux/UNIX" \
  --query 'SpotPriceHistory[0].SpotPrice'

# Set higher max price in terraform.tfvars
spot_max_price = "0.15"
```

### Cannot Connect to Lab Server via VPN

```bash
# Verify VPN is connected
sudo wg show

# Check lab server security group allows VPN subnet
aws ec2 describe-security-groups \
  --filters Name=tag:Name,Values=containerlab-lab-sg

# Ping lab server from VPN client
ping 10.0.1.100

# If ping works but SSH doesn't, check SSH service on lab server
# (Connect via VPN server as jump host)
ssh -J ubuntu@<VPN_IP> ubuntu@10.0.1.100
```

### Cannot Access cEOS Instances Directly

```bash
# 1. Verify VPN is connected and routes are in place
sudo wg show
ip route | grep 172.20

# You should see: 172.20.0.0/16 via VPN interface

# 2. Test connectivity to lab server first
ping 10.0.1.100

# 3. Check if containerlab is running
ssh ubuntu@10.0.1.100 "sudo containerlab inspect --all"

# 4. Verify IP forwarding on lab server
ssh ubuntu@10.0.1.100 "sysctl net.ipv4.ip_forward"
# Should return: net.ipv4.ip_forward = 1

# 5. Check routing on VPN server
ssh ubuntu@<VPN_IP> "ip route | grep 172.20"
# Should show: 172.20.0.0/16 via 10.0.1.100

# 6. Test from lab server (should work)
ssh ubuntu@10.0.1.100 "ping -c 2 172.20.20.2"

# 7. Verify WireGuard AllowedIPs includes containerlab network
cat ~/wireguard-containerlab.conf | grep AllowedIPs
# Should include: 172.20.0.0/16

# If AllowedIPs is wrong, get new config:
ssh ubuntu@<VPN_IP> cat /home/ubuntu/client1.conf > wireguard-containerlab.conf
sudo wg-quick down wireguard-containerlab.conf
sudo wg-quick up wireguard-containerlab.conf
```

### Lab Server Out of Memory

```bash
# Check memory usage
free -h

# Check running containers
docker ps

# Stop unused containers
docker stop $(docker ps -q)

# Or upgrade instance type in terraform.tfvars
lab_instance_type = "r7i.2xlarge"
terraform apply
```

### Disk Space Issues

```bash
# Check disk usage
df -h

# Clean Docker
docker system prune -a --volumes

# Or increase disk size in terraform.tfvars
lab_disk_size = 200
terraform apply
```

## Advanced Configuration

### Add More VPN Clients

```bash
# SSH to VPN server
ssh ubuntu@<VPN_IP>

# Generate new client keys
cd /etc/wireguard
sudo wg genkey | sudo tee client2_private.key | sudo wg pubkey | sudo tee client2_public.key

# Add to server config
sudo vim /etc/wireguard/wg0.conf
# Add peer section with new public key

# Restart WireGuard
sudo systemctl restart wg-quick@wg0

# Create client config with new private key
```

### Use Different Region

```hcl
# terraform.tfvars
aws_region = "us-west-2"
```

### Enable S3 Backend (Team Use)

```hcl
# backend.tf
terraform {
  backend "s3" {
    bucket = "my-terraform-state"
    key    = "containerlab/terraform.tfstate"
    region = "us-east-1"
  }
}
```

## Security Considerations

1. **SSH Keys**: Never commit private keys to version control
2. **IP Restrictions**: Update `admin_ip` when your IP changes
3. **VPN Keys**: Rotate WireGuard keys periodically
4. **Spot Instances**: Lab server uses spot (can be interrupted). VPN uses on-demand for reliability.
5. **Destroy When Done**: Minimize attack surface
6. **Lab Server Security**: While in public subnet, security groups ensure it's only accessible via VPN. No services are exposed to the internet.
7. **Save Work Regularly**: With spot instances, save containerlab configs and important data frequently

## Monitoring Costs

```bash
# View current month costs
aws ce get-cost-and-usage \
  --time-period Start=$(date +%Y-%m-01),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost

# Set up billing alert
aws budgets create-budget \
  --account-id $(aws sts get-caller-identity --query Account --output text) \
  --budget file://budget.json
```

## Project Structure

```
.
├── main.tf                    # Core infrastructure
├── variables.tf               # Input variables
├── outputs.tf                 # Output values
├── terraform.tfvars.example   # Example configuration
├── terraform.tfvars           # Your config (git ignored)
├── wireguard-setup.sh         # VPN server setup
├── lab-setup.sh               # Lab server setup
└── README.md                  # This file
```

## Network Reference

**IP Allocations:**
```
VPN Clients:           10.13.13.0/24
  - VPN Server:        10.13.13.1
  - Client 1:          10.13.13.2
  - Additional clients: 10.13.13.3+

AWS VPC:               10.0.0.0/16
  - Public Subnet:     10.0.1.0/24
  - VPN Server:        10.0.1.x (dynamic)
  - Lab Server:        10.0.1.100 (static)

Containerlab:          172.20.0.0/16 (routed via VPN)
  - Default mgmt:      172.20.20.0/24
  - Available for use: 172.20.0.0 - 172.20.255.255
```

**Routing:**
- VPN clients → 172.20.0.0/16 → VPN server → Lab server → Docker containers
- All traffic encrypted through WireGuard tunnel
- No NAT required for containerlab access

**Ports:**
- WireGuard VPN: UDP/51820
- SSH to VPN: TCP/22 (restricted to admin_ip)
- SSH to Lab: TCP/22 (from VPN network only)
- cEOS SSH: TCP/22 on 172.20.x.x (via VPN)
- cEOS APIs: Various ports on 172.20.x.x (via VPN)

## Support Resources

- **Containerlab Docs**: https://containerlab.dev
- **Arista cEOS**: https://www.arista.com/en/support/software-download
- **WireGuard**: https://www.wireguard.com/install/
- **Terraform AWS Provider**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs

## License

This infrastructure code is provided as-is for educational and testing purposes.
