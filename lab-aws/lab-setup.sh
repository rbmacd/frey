#!/bin/bash
set -e

# Wait for cloud-init to finish
#cloud-init status --wait

# Update system
apt-get update
apt-get upgrade -y

# Enable IP forwarding for routing between VPN and containerlab networks
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p

# Configure iptables to allow forwarding between VPN clients and Docker networks
iptables -A FORWARD -s 10.13.13.0/24 -j ACCEPT
iptables -A FORWARD -d 10.13.13.0/24 -j ACCEPT

# Save iptables rules
iptables-save > /etc/iptables.rules

# Create script to restore iptables on boot
cat > /etc/network/if-pre-up.d/iptables <<'EOFW'
#!/bin/sh
iptables-restore < /etc/iptables.rules
EOFW
chmod +x /etc/network/if-pre-up.d/iptables

# Install dependencies
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    git \
    vim \
    tmux \
    htop \
    iperf3 \
    tcpdump \
    net-tools

# Install Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add ubuntu user to docker group
usermod -aG docker ubuntu

# Enable and start Docker
systemctl enable docker
systemctl start docker

# Install containerlab
sudo bash -c "$(curl -sL https://get.containerlab.dev)"

# Create workspace directory
mkdir -p /home/ubuntu/containerlab-labs
chown ubuntu:ubuntu /home/ubuntu/containerlab-labs

# Create example topology file for Arista cEOS - RM TO UPDATE LATER WITH GIT CALL
cat > /home/ubuntu/containerlab-labs/example-topology.yaml <<'EOF'
name: arista-lab

topology:
  nodes:
    spine1:
      kind: ceos
      image: ceos:latest
      mgmt-ipv4: 172.20.20.2
      
    spine2:
      kind: ceos
      image: ceos:latest
      mgmt-ipv4: 172.20.20.3
      
    leaf1:
      kind: ceos
      image: ceos:latest
      mgmt-ipv4: 172.20.20.4
      
    leaf2:
      kind: ceos
      image: ceos:latest
      mgmt-ipv4: 172.20.20.5

  links:
    # Spine1 to Leafs
    - endpoints: ["spine1:eth1", "leaf1:eth1"]
    - endpoints: ["spine1:eth2", "leaf2:eth1"]
    
    # Spine2 to Leafs
    - endpoints: ["spine2:eth1", "leaf1:eth2"]
    - endpoints: ["spine2:eth2", "leaf2:eth2"]
    
    # Leaf to Leaf (optional)
    - endpoints: ["leaf1:eth3", "leaf2:eth3"]

mgmt:
  network: custom-mgmt
  ipv4-subnet: 172.20.20.0/24
EOF

chown ubuntu:ubuntu /home/ubuntu/containerlab-labs/example-topology.yaml

# Create README with instructions
cat > /home/ubuntu/README.txt <<'EOF'
=== CONTAINERLAB SERVER SETUP COMPLETE ===

This server is ready for network simulations using containerlab and Arista cEOS.

IMPORTANT: Before using containerlab, you need to import the Arista cEOS image.

== DIRECT NETWORK ACCESS ==

This lab server is configured to allow VPN clients DIRECT access to containerlab networks.
When you connect via VPN, you can access cEOS instances at their management IP addresses.

Network routing:
- VPN clients: 10.13.13.0/24
- Lab server: 10.0.1.100
- Containerlab management: 172.20.0.0/16 (routed through VPN)

This means you can:
- SSH directly to cEOS instances: ssh admin@172.20.20.2
- Ping devices: ping 172.20.20.3
- Use network tools: traceroute, telnet, netcat, etc.
- Access web interfaces if enabled
- Connect network management tools directly

== GETTING ARISTA cEOS IMAGE ==

1. Download cEOS image from Arista (requires free account):
   https://www.arista.com/en/support/software-download
   
   - Register for a free account
   - Navigate to cEOS-lab images
   - Download the latest cEOS64 image (e.g., cEOS64-lab-4.XX.X.tar.xz)

2. Transfer the image to this server (from your local machine):
   scp cEOS64-lab-4.XX.X.tar.xz ubuntu@THIS_SERVER_IP:~/

3. Import the image into Docker:
   docker import cEOS64-lab-4.XX.X.tar.xz ceos:latest
   
   Or with specific version:
   docker import cEOS64-lab-4.XX.X.tar.xz ceos:4.XX.X

== QUICK START ==

1. Verify containerlab installation:
   sudo containerlab version

2. Check example topology:
   cd ~/containerlab-labs
   cat example-topology.yaml

3. Deploy the topology (after importing cEOS image):
   sudo containerlab deploy -t example-topology.yaml

4. List running labs:
   sudo containerlab inspect --all

5. Access a device:
   ssh admin@172.20.20.2
   (default password: admin)

6. Destroy the topology:
   sudo containerlab destroy -t example-topology.yaml

== USEFUL COMMANDS ==

# View Docker images
docker images

# View running containers
docker ps

# Check container logs
docker logs <container-name>

# Connect to container shell
docker exec -it <container-name> /bin/bash

# View containerlab graphs
sudo containerlab graph -t example-topology.yaml

== SYSTEM RESOURCES ==

# Check memory usage
free -h

# Check disk usage
df -h

# Monitor system resources
htop

== TIPS ==

- Each cEOS container uses ~1-2 GB RAM
- Start with small topologies and scale up
- Use tmux for persistent sessions
- Save your topologies in ~/containerlab-labs/
- Export configs before destroying topologies

== DOCUMENTATION ==

Containerlab: https://containerlab.dev
Arista cEOS: https://www.arista.com/en/support/software-download

EOF

chown ubuntu:ubuntu /home/ubuntu/README.txt

# Optimize Docker for containerlab
cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-address-pools": [
    {
      "base": "172.20.0.0/16",
      "size": 24
    }
  ]
}
EOF

systemctl restart docker

# Print completion message to system log
echo "Lab server setup complete! See /home/ubuntu/README.txt for instructions." | tee /dev/kmsg

echo "Setup complete!"