#!/bin/bash
set -e

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
    net-tools \
    jq \
    awscli

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
bash -c "$(curl -sL https://get.containerlab.dev)"

# Download cEOS image from S3 if available
# Wait for EC2 metadata service to be ready
echo "Checking EC2 metadata service availability..."
METADATA_READY=false
for i in {1..30}; do
    if curl -s -f -m 1 http://169.254.169.254/latest/meta-data/ >/dev/null 2>&1; then
        echo "Metadata service is available"
        METADATA_READY=true
        break
    fi
    echo "Waiting for metadata service... attempt $i/30"
    sleep 2
done

if [ "$METADATA_READY" = false ]; then
    echo "Warning: Metadata service not available after 60 seconds"
    echo "Skipping S3 cEOS image download"
else
    # Get AWS account ID from EC2 instance identity document (no credentials needed!)
    echo "Retrieving AWS account ID from instance metadata..."
    ACCOUNT_ID=$(curl -s http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r '.accountId')
    
    if [ -n "$ACCOUNT_ID" ] && [ "$ACCOUNT_ID" != "null" ] && [ "$ACCOUNT_ID" != "None" ]; then
        echo "Successfully retrieved AWS account ID: $ACCOUNT_ID"
        
        S3_BUCKET="containerlab-tfstate-$${ACCOUNT_ID}"
        CEOS_IMAGE="ceos-latest.tar.xz"
        
        echo "Attempting to download cEOS image from S3..."
        echo "Bucket: s3://$${S3_BUCKET}/images/$${CEOS_IMAGE}"
        
        # Wait a bit for IAM credentials to be available (credentials are separate from account ID)
        echo "Waiting for IAM role credentials to be available..."
        sleep 10
        
        # Attempt S3 download with retries
        MAX_RETRIES=5
        RETRY_COUNT=0
        DOWNLOAD_SUCCESS=false
        
        while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
            if aws s3 cp s3://$${S3_BUCKET}/images/$${CEOS_IMAGE} /tmp/$${CEOS_IMAGE} 2>&1; then
                echo "cEOS image downloaded successfully from S3"
                echo "Importing cEOS image into Docker..."
                docker import /tmp/$${CEOS_IMAGE} ceos:latest
                rm /tmp/$${CEOS_IMAGE}
                echo "cEOS image imported successfully!"
                echo "Run 'docker images' to verify"
                DOWNLOAD_SUCCESS=true
                break
            else
                RETRY_COUNT=$((RETRY_COUNT + 1))
                if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
                    echo "Download attempt $RETRY_COUNT failed, waiting 10 seconds before retry..."
                    sleep 10
                fi
            fi
        done
        
        if [ "$DOWNLOAD_SUCCESS" = false ]; then
            echo "Could not download cEOS image from S3 after $MAX_RETRIES attempts"
            echo "Possible reasons:"
            echo "  1. Image not uploaded yet: aws s3 cp cEOS.tar.xz s3://$${S3_BUCKET}/images/ceos-latest.tar.xz"
            echo "  2. IAM permissions issue - check IAM role attached to instance"
            echo "  3. Bucket does not exist"
            echo ""
            echo "You can upload the cEOS image manually later."
            echo "To debug IAM role: aws sts get-caller-identity"
        fi
    else
        echo "Could not retrieve AWS account ID from instance metadata"
        echo "cEOS image will need to be imported manually:"
        echo "  scp cEOS.tar.xz ubuntu@<lab-ip>:~/"
        echo "  docker import cEOS.tar.xz ceos:latest"
    fi
fi

# Create workspace directory
mkdir -p /home/ubuntu/containerlab-labs
chown ubuntu:ubuntu /home/ubuntu/containerlab-labs

# Download example topology from URL if configured
TOPOLOGY_URL="${example_topology_url}"

if [ -n "$TOPOLOGY_URL" ]; then
    echo "Downloading example topology from: $TOPOLOGY_URL"
    if curl -fsSL "$TOPOLOGY_URL" -o /home/ubuntu/containerlab-labs/example-topology.yaml; then
        chown ubuntu:ubuntu /home/ubuntu/containerlab-labs/example-topology.yaml
        echo "Example topology downloaded successfully!"
    else
        echo "Warning: Could not download example topology from $TOPOLOGY_URL"
        echo "You can manually create topology files in ~/containerlab-labs/"
    fi
else
    echo "No example topology URL configured. Create your own in ~/containerlab-labs/"
fi

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

2. Check example topology (downloaded from GitHub):
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

Note: The example topology is downloaded from:
${example_topology_url}

You can create your own topologies in ~/containerlab-labs/

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

# Start containerlab topology
sudo containerlab deploy -t /home/ubuntu/containerlab-labs/example-topology.yaml &

# Print completion message to system log
echo "Lab server setup complete! See /home/ubuntu/README.txt for instructions." | tee /dev/kmsg

echo "Setup complete!"