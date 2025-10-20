#!/bin/bash
set -e

# Wait for cloud-init to finish
cloud-init status --wait

# Update system
apt-get update
apt-get upgrade -y

# Install WireGuard
apt-get install -y wireguard wireguard-tools

# Enable IP forwarding
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf
sysctl -p

# Generate server keys
cd /etc/wireguard
umask 077
wg genkey | tee server_private.key | wg pubkey > server_public.key

# Generate client keys
wg genkey | tee client1_private.key | wg pubkey > client1_public.key

# Get server private key
SERVER_PRIVATE_KEY=$(cat server_private.key)
CLIENT1_PUBLIC_KEY=$(cat client1_public.key)
CLIENT1_PRIVATE_KEY=$(cat client1_private.key)
SERVER_PUBLIC_KEY=$(cat server_public.key)

# Get public IP
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

# Create WireGuard server config
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.13.13.1/24
ListenPort = 51820
PrivateKey = $SERVER_PRIVATE_KEY

# Enable packet forwarding for VPN and containerlab networks
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostUp = ip route add 172.20.0.0/16 via ${lab_server_ip} || true
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
PostDown = ip route del 172.20.0.0/16 via ${lab_server_ip} || true

# Client 1
[Peer]
PublicKey = $CLIENT1_PUBLIC_KEY
AllowedIPs = 10.13.13.2/32
EOF

# Create client config
cat > /home/ubuntu/client1.conf <<EOF
[Interface]
PrivateKey = $CLIENT1_PRIVATE_KEY
Address = 10.13.13.2/24
DNS = 1.1.1.1

[Peer]
PublicKey = $SERVER_PUBLIC_KEY
Endpoint = $PUBLIC_IP:51820
# AllowedIPs includes:
# - VPN network (10.13.13.0/24)
# - AWS VPC (10.0.0.0/16) for lab server access
# - Containerlab networks (172.20.0.0/16) for direct cEOS access
AllowedIPs = 10.0.0.0/16, 10.13.13.0/24, 172.20.0.0/16
PersistentKeepalive = 25
EOF

# Set proper permissions
chmod 600 /etc/wireguard/wg0.conf
chmod 600 /home/ubuntu/client1.conf
chown ubuntu:ubuntu /home/ubuntu/client1.conf

# Enable and start WireGuard
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0

# Create instructions file
cat > /home/ubuntu/README.txt <<EOF
WireGuard VPN Server Setup Complete!

Client configuration file: /home/ubuntu/client1.conf

To retrieve the config:
  cat /home/ubuntu/client1.conf

Copy this config to your local machine and import it into your WireGuard client.

WireGuard downloads:
  - Windows/Mac/Linux: https://www.wireguard.com/install/
  - iOS: App Store
  - Android: Google Play Store

After connecting, you can access:
  - Lab server: ${lab_server_ip}
  - Containerlab networks: 172.20.0.0/16 (direct access to cEOS instances)

The VPN is configured to route containerlab management traffic (172.20.x.x) 
directly to your cEOS instances. You can SSH, ping, or use network tools 
directly against cEOS management IPs.

Example: If you deploy a topology with spine1 at 172.20.20.2:
  ssh admin@172.20.20.2

To add more clients:
  1. Generate new keys: wg genkey | tee clientN_private.key | wg pubkey > clientN_public.key
  2. Add peer to /etc/wireguard/wg0.conf
  3. Restart: systemctl restart wg-quick@wg0
EOF

chown ubuntu:ubuntu /home/ubuntu/README.txt

echo "WireGuard setup complete!"