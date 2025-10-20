# Direct Network Access to Containerlab

This infrastructure provides **direct IP connectivity** from your laptop to Arista cEOS instances running in containerlab on AWS. No SSH tunneling, port forwarding, or jump hosts required!

## How It Works

### Network Architecture

```
Your Laptop (10.13.13.2)
    ↓ [WireGuard VPN Tunnel]
VPN Server (configurable, default: t3.micro) in AWS
    ↓ [Routing via 10.0.1.100]
Lab Server (configurable, default: r7i.xlarge spot)
    ↓ [Docker Bridge]
Containerlab Network (172.20.20.0/24)
    ├─ spine1: 172.20.20.2
    ├─ spine2: 172.20.20.3
    ├─ leaf1:  172.20.20.4
    └─ leaf2:  172.20.20.5
```

### Traffic Flow

1. **Your laptop** sends packet to `172.20.20.2`
2. **WireGuard** encrypts and routes it through VPN tunnel
3. **VPN Server** receives packet and routes to lab server `10.0.1.100`
4. **Lab Server** forwards to Docker network `172.20.20.0/24`
5. **cEOS instance** receives packet directly

All handled automatically - you just use the IP addresses!

## Configuration Details

### VPN Server Configuration

The VPN server is configured to:
- Route `172.20.0.0/16` to lab server (`10.0.1.100`)
- Forward packets between VPN clients and lab server
- Maintain routing table for containerlab networks

```bash
# On VPN server, you'll see:
ip route | grep 172.20
# Output: 172.20.0.0/16 via 10.0.1.100 dev eth0
```

### Lab Server Configuration

The lab server is configured to:
- Enable IP forwarding (`net.ipv4.ip_forward=1`)
- Accept traffic from VPN subnet (`10.13.13.0/24`)
- Forward between Docker networks and VPN clients

### Client Configuration

Your WireGuard client config includes:
```ini
[Interface]
PrivateKey = <your-key>
Address = 10.13.13.2/24

[Peer]
PublicKey = <vpn-server-key>
Endpoint = <vpn-ip>:51820
AllowedIPs = 10.0.0.0/16, 10.13.13.0/24, 172.20.0.0/16
```

The key is `AllowedIPs = 172.20.0.0/16` - this tells WireGuard to route containerlab traffic through the VPN.

## Verification Steps

### 1. Check VPN Connection

```bash
# Verify VPN is up
sudo wg show

# Check routing table
ip route | grep 172.20
# Should output: 172.20.0.0/16 dev wg0 scope link
```

### 2. Test Lab Server Connectivity

```bash
# Ping lab server
ping 10.0.1.100

# SSH to lab server
ssh ubuntu@10.0.1.100
```

### 3. Deploy Containerlab Topology

```bash
# On lab server
sudo containerlab deploy -t ~/containerlab-labs/example-topology.yaml

# Check what IPs were assigned
sudo containerlab inspect --all
```

### 4. Test Direct Access to cEOS

```bash
# From your laptop (not lab server!)
ping 172.20.20.2

# SSH directly to cEOS
ssh admin@172.20.20.2
# Password: admin

# If you get in, it worked! 🎉
```

## Common Use Cases

### SSH Access

```bash
# Direct SSH to any device
ssh admin@172.20.20.2
ssh admin@172.20.20.3
ssh admin@172.20.20.4

# Use with SSH config
cat >> ~/.ssh/config <<EOF
Host ceos-spine1
    HostName 172.20.20.2
    User admin
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
EOF

ssh ceos-spine1
```

### Ansible Automation

```yaml
# inventory.yml
all:
  children:
    spines:
      hosts:
        spine1:
          ansible_host: 172.20.20.2
        spine2:
          ansible_host: 172.20.20.3
    leafs:
      hosts:
        leaf1:
          ansible_host: 172.20.20.4
        leaf2:
          ansible_host: 172.20.20.5
  vars:
    ansible_user: admin
    ansible_password: admin
    ansible_network_os: eos
    ansible_connection: network_cli
```

```bash
# Run playbook directly
ansible-playbook -i inventory.yml deploy-configs.yml
```

### NAPALM Testing

```python
from napalm import get_network_driver

driver = get_network_driver('eos')
device = driver(
    hostname='172.20.20.2',
    username='admin',
    password='admin',
    optional_args={'enable_password': 'admin'}
)

device.open()
facts = device.get_facts()
print(facts)
device.close()
```

### Nornir Workflows

```python
from nornir import InitNornir
from nornir_napalm.plugins.tasks import napalm_get

nr = InitNornir(
    inventory={
        "plugin": "SimpleInventory",
        "options": {
            "host_file": "hosts.yaml",
        }
    }
)

result = nr.run(task=napalm_get, getters=["get_facts"])
print(result)
```

### REST API Access

```python
import requests
from requests.auth import HTTPBasicAuth

# If you enable eAPI on cEOS
url = "http://172.20.20.2/command-api"
auth = HTTPBasicAuth('admin', 'admin')

payload = {
    "jsonrpc": "2.0",
    "method": "runCmds",
    "params": {
        "version": 1,
        "cmds": ["show version"],
        "format": "json"
    },
    "id": 1
}

response = requests.post(url, json=payload, auth=auth)
print(response.json())
```

### Network Testing Tools

```bash
# MTR (traceroute + ping)
mtr 172.20.20.2

# Nmap scanning
nmap -p 22,80,443 172.20.20.2-10

# Netcat
nc -zv 172.20.20.2 22

# Traceroute
traceroute 172.20.20.2

# TCPDump (on your laptop!)
sudo tcpdump -i wg0 host 172.20.20.2
```

## Multiple Topologies

You can run multiple containerlab topologies simultaneously, each with its own subnet:

```yaml
# topology1.yaml
name: datacenter-spine-leaf
mgmt:
  network: dc-lab
  ipv4-subnet: 172.20.10.0/24

# topology2.yaml
name: campus-network
mgmt:
  network: campus-lab
  ipv4-subnet: 172.20.20.0/24

# topology3.yaml
name: wan-edge
mgmt:
  network: wan-lab
  ipv4-subnet: 172.20.30.0/24
```

All subnets within `172.20.0.0/16` are automatically routed through the VPN!

## Troubleshooting

### Can't Reach cEOS Instances

```bash
# 1. Is VPN connected?
sudo wg show
# Should show interface wg0 with data transfer

# 2. Are routes correct?
ip route | grep 172.20
# Should show route via wg0

# 3. Can you reach lab server?
ping 10.0.1.100
# Should respond

# 4. Is containerlab running?
ssh ubuntu@10.0.1.100 "sudo containerlab inspect --all"
# Should list running containers

# 5. Check from lab server
ssh ubuntu@10.0.1.100 "ping 172.20.20.2"
# If this works but your laptop can't reach it, routing issue

# 6. Check WireGuard AllowedIPs
cat ~/wireguard-containerlab.conf | grep AllowedIPs
# Must include: 172.20.0.0/16
```

### Routing Issues

```bash
# On VPN server
ssh ubuntu@<VPN_IP>
ip route show | grep 172.20
# Should show: 172.20.0.0/16 via 10.0.1.100

# On lab server
ssh ubuntu@10.0.1.100
sudo sysctl net.ipv4.ip_forward
# Should return: net.ipv4.ip_forward = 1

sudo iptables -L FORWARD -n
# Should show rules accepting traffic from 10.13.13.0/24
```

### Missing AllowedIPs

If your client config doesn't include `172.20.0.0/16`:

```bash
# Disconnect VPN
sudo wg-quick down wireguard-containerlab.conf

# Get fresh config
ssh ubuntu@<VPN_IP> cat /home/ubuntu/client1.conf > wireguard-new.conf

# Verify it includes 172.20.0.0/16
grep AllowedIPs wireguard-new.conf

# Connect with new config
sudo wg-quick up wireguard-new.conf
```

## Network Limits

The VPN routes `172.20.0.0/16` which provides:
- 65,536 IP addresses total
- 256 /24 subnets
- Plenty of space for hundreds of topologies

**Recommended subnet allocation:**
- `172.20.0.0/24` - Reserved
- `172.20.10.0/24` - Datacenter topologies
- `172.20.20.0/24` - Campus topologies (default)
- `172.20.30.0/24` - WAN topologies
- `172.20.40.0/24` - Service provider topologies
- ... and so on

## Security Considerations

**What's secured:**
- All traffic encrypted via WireGuard
- Lab server only accessible from VPN
- No public exposure of cEOS instances

**What's not secured:**
- cEOS instances trust VPN clients (use auth!)
- Default credentials (`admin/admin`) should be changed for sensitive work
- Internal network traffic between containers is not encrypted

**Best practices:**
- Change default cEOS passwords
- Use SSH keys instead of passwords
- Rotate WireGuard keys periodically
- Limit VPN client IPs to specific users
- Monitor VPN access logs

## Performance

**Latency:**
- Your location → AWS: Varies by region
- Typical: 20-100ms depending on distance
- VPN overhead: ~1-2ms
- Total: Usually < 100ms

**Throughput:**
- WireGuard is very efficient
- Limited by your internet upload speed
- Typical: 100+ Mbps through VPN
- More than sufficient for network automation

**Tips for best performance:**
- Choose AWS region closest to you
- Use wired internet connection
- Consider placement groups for lab server (if needed)

## Advanced: CI/CD Integration

You can use this setup in CI/CD pipelines:

```yaml
# GitHub Actions example
name: Test Network Config

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup WireGuard
        run: |
          sudo apt-get install -y wireguard
          echo "${{ secrets.WG_CONFIG }}" > wg0.conf
          sudo wg-quick up ./wg0.conf
      
      - name: Test connectivity
        run: |
          ping -c 2 172.20.20.2
      
      - name: Deploy configs
        run: |
          ansible-playbook -i inventory.yml deploy.yml
      
      - name: Run tests
        run: |
          python test_network.py
      
      - name: Cleanup
        run: sudo wg-quick down ./wg0.conf
```

## Summary

This setup provides **true direct IP connectivity** to your containerlab networks:

✅ No SSH tunneling needed
✅ No port forwarding needed  
✅ No jump hosts needed
✅ Use any tool that requires IP connectivity
✅ Perfect for automation and testing
✅ Secure via WireGuard VPN
✅ Simple to understand and troubleshoot

The routing is automatic once VPN is connected - just use the IP addresses!
