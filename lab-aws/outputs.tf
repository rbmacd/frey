output "vpn_server_instance_type" {
  description = "Instance type used for VPN server"
  value       = var.vpn_instance_type
}

output "lab_server_instance_type" {
  description = "Instance type used for lab server"
  value       = var.lab_instance_type
}

output "vpn_server_public_ip" {
  description = "Public IP of VPN server"
  value       = aws_eip.vpn.public_ip
}

output "vpn_server_ssh" {
  description = "SSH command for VPN server"
  value       = "ssh ubuntu@${aws_eip.vpn.public_ip}"
}

output "lab_server_ip" {
  description = "IP address of lab server (accessible via VPN only)"
  value       = aws_instance.lab.private_ip
}

output "lab_server_ssh_via_vpn" {
  description = "SSH command for lab server (connect to VPN first)"
  value       = "ssh ubuntu@${aws_instance.lab.private_ip}"
}

output "wireguard_config_location" {
  description = "Location of WireGuard client config on VPN server"
  value       = "/home/ubuntu/client1.conf"
}

output "setup_instructions" {
  description = "Next steps to complete setup"
  value       = <<-EOT
    
    === SETUP INSTRUCTIONS ===
    
    DEPLOYED CONFIGURATION:
    - VPN Server: ${var.vpn_instance_type} (on-demand, always available)
    - Lab Server: ${var.lab_instance_type} (spot instance, cost-optimized)
    
    1. SSH into VPN server:
       ssh ubuntu@${aws_eip.vpn.public_ip}
    
    2. Retrieve WireGuard client config:
       cat /home/ubuntu/client1.conf
    
    3. Save the config to your local machine and import into WireGuard client
       Download WireGuard: https://www.wireguard.com/install/
    
    4. Connect to VPN and access lab server:
       ssh ubuntu@${aws_instance.lab.private_ip}
    
    5. On lab server, containerlab is pre-installed. Start using:
       sudo containerlab deploy -t your-topology.yaml
    
    === COST TRACKING ===
    Monitor costs at: https://console.aws.amazon.com/cost-management/
    
    === SPOT INSTANCE INFO ===
    Lab server uses spot pricing for maximum cost savings.
    Interruption rate: <5% (very rare for r-family instances)
    If interrupted, simply run 'terraform apply' again to redeploy.
    
    === TEARDOWN ===
    When done, destroy all resources:
       terraform destroy -auto-approve
    
  EOT
}

output "estimated_hourly_cost" {
  description = "Estimated hourly cost (USD)"
  value       = "See cost breakdown in README"
}