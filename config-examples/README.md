# Frey Network Config Management - Setup Guide
## AWX + NetBox + Ansible + Jinja2 Integration

**Purpose**: Examples of centralized configuration management for network devices using NetBox as source of truth and AWX for execution. Part of the Frey project initiative.

---

## Quick Start Guide

### Complete End-to-End Workflow (5 Minutes)

For the fastest path from zero to a running VXLAN/EVPN fabric:

```bash
# 1. Clone repository
git clone https://github.com/yourusername/frey-netcfg-mgmt.git
cd frey-netcfg-mgmt

# 2. Install dependencies
pip install -r requirements.txt
ansible-galaxy collection install arista.eos netbox.netbox

# 3. Set NetBox credentials
export NETBOX_URL=https://netbox.example.com
export NETBOX_APITOKEN=your_token_here

# 4. Seed NetBox from containerlab topology
python scripts/seed_netbox_from_clab.py containerlab/frey-lab.clab.yml

# 5. Deploy containerlab
cd containerlab
sudo containerlab deploy -t frey-lab.clab.yml

# 6. In AWX UI:
#    - Sync NetBox inventory
#    - Run "Generate - Arista Configs" (limit: sites_frey_netcfg_lab)
#    - Run "Deploy - Arista Configs" (limit: sites_frey_netcfg_lab)

# 7. Verify
ssh admin@172.20.20.2  # password: admin
show ip bgp summary
show bgp evpn summary
```

**Result**: Fully functional spine-leaf VXLAN/EVPN fabric running in containerlab, configured via NetBox and AWX.

---

## Table of Contents

1. [Quick Start Guide](#quick-start-guide)
2. [Architecture Overview](#architecture-overview)
3. [Prerequisites](#prerequisites)
4. [Repository Setup](#repository-setup)
5. [AWX Configuration](#awx-configuration)
6. [NetBox Integration](#netbox-integration)
7. [Testing & Validation](#testing--validation)
8. [Workflow](#workflow)
9. [Troubleshooting](#troubleshooting)
10. [Best Practices](#best-practices)
11. [Quick Reference](#quick-reference)
12. [Next Steps](#next-steps)
13. [Additional Resources](#additional-resources)

---

## Architecture Overview

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   NetBox    │────────▶│     AWX     │────────▶│   Arista    │
│ Source of   │         │  Execution  │         │   Devices   │
│   Truth     │         │   Engine    │         │   (cEOS)    │
└─────────────┘         └─────────────┘         └─────────────┘
      │                       │                        │
      │                       │                        │
      │                 ┌─────▼─────┐                  │
      └────────────────▶│    Git    │◀─────────────────┘
                        │Repository │
                        └───────────┘
```

**Components**:
- **NetBox**: Single source of truth (devices, interfaces, IPs, VLANs, config context)
  - **Critical**: All device-specific data lives here, NOT in Git
- **AWX**: Job execution, scheduling, credentials management, inventory sync
  - Pulls inventory dynamically from NetBox
  - The static inventory file in Git is ONLY for local testing
- **Git**: Version control for templates, playbooks, and organizational defaults
  - Contains HOW to configure devices (templates)
  - Contains WHEN/HOW to execute (playbooks)
  - Contains organizational standards (default NTP, banners, etc.)
  - Does NOT contain device-specific data (that's in NetBox)
- **Jinja2**: Configuration templating engine
- **Ansible**: Automation framework with arista.eos collection
- **Containerlab**: Testing environment with Arista cEOS containers

**Key Architectural Principle**: 
- NetBox = WHAT to configure (the data)
- Git = HOW to configure (the templates and logic)
- AWX = WHEN to configure (execution and orchestration)

### Quick Reference: What Goes Where

| Data Type | Store In | Example |
|-----------|----------|---------|
| Device hostnames, IPs | NetBox | spine01, 10.0.0.1 |
| Interface configs | NetBox config context | Ethernet1, description, IP |
| VLANs | NetBox config context | VLAN 10, name: DATA |
| BGP neighbors | NetBox config context | Peer IPs, ASNs |
| Site-specific NTP/DNS | NetBox config context | DC1 NTP servers |
| Device-specific syslog | NetBox config context | Per-device syslog targets |
| Organizational metadata | Git group_vars/all.yml (optional) | Project name, contact email |
| Banner logic | Git templates/ | Role-based banner conditionals |
| Config templates | Git templates/ | How to render EOS config |
| Automation playbooks | Git playbooks/ | Backup, generate, deploy |
| Ansible connection | Git group_vars/platforms_eos.yml | ansible_network_os: eos |
| Policy by role (rare) | Git group_vars/device_roles_*.yml | Border routers must use TACACS |
| Passwords/secrets | AWX credentials | Device passwords, tokens |
| Local test inventory | Git inventory/hosts.yml | Only for testing without AWX |

---

## Prerequisites

### Required Software
- Python 3.8+
- Ansible 2.15+
- Git
- AWX/Ansible Tower (with NetBox dynamic inventory already configured)
- Containerlab (for testing only)
- Arista cEOS image (for testing only)

### Required Access
- NetBox instance with populated Arista devices
- AWX instance with admin access
- Git repository (GitHub, GitLab, etc.)
- Network access to Arista devices

### Ansible Collections
```bash
ansible-galaxy collection install arista.eos
ansible-galaxy collection install netbox.netbox
```

### Helper Scripts

**NetBox Seeding Script** (`scripts/seed_netbox_from_clab.py`):

This script automates the process of populating NetBox from a containerlab topology file. It creates:
- Devices with appropriate roles (auto-detected from hostname patterns)
- Interfaces and physical links
- Management IP addresses
- Platform assignments (Arista EOS)
- **Config context with complete BGP/EVPN/VXLAN configuration**

**Installation**:
```bash
# Dependencies already in requirements.txt
pip install -r requirements.txt

# Place script in scripts/ directory
# Available at: https://github.com/rbmacd/frey-netcfg-mgmt/
```

**Usage**:
```bash
export NETBOX_URL=https://netbox.example.com
export NETBOX_APITOKEN=your_token

python scripts/seed_netbox_from_clab.py containerlab/frey-lab.clab.yml
```

**Configuration Generated**:
- **Spines**: BGP AS 65000, Router IDs 10.255.255.1+, EVPN route reflectors
- **Leafs**: BGP AS 65001+, Router IDs 10.255.255.11+, VTEP configuration
- **VLANs**: Default VLANs 10 (DATA), 20 (VOICE), 30 (GUEST)
- **VNI Mappings**: VLAN+10000 (VLAN 10 → VNI 10010)
- **BGP Neighbors**: Auto-discovered from topology links

---

## Repository Setup

### Step 1: Initialize Directory Structure

```bash
# Create project directory
mkdir frey-netcfg-mgmt && cd frey-netcfg-mgmt
git init

# Create directory tree
mkdir -p playbooks
mkdir -p templates
mkdir -p configs/backup
mkdir -p configs/generated
mkdir -p group_vars
mkdir -p host_vars
mkdir -p inventory
mkdir -p scripts
mkdir -p containerlab
mkdir -p docs

# Create essential files
touch README.md
touch .gitignore
touch ansible.cfg
touch requirements.txt

# Create required group_vars file
touch group_vars/platforms_eos.yml

# Note: seed_netbox_from_clab.py should be placed in scripts/
# Download from: https://github.com/rbmacd/frey or create from provided code

# Optional: Create group_vars/all.yml if you need organizational metadata
# or are in a migration period. For pure NetBox implementations, omit this file.
# touch group_vars/all.yml

# Note: Only create device_roles_*.yml files if you have
# genuine organizational policy differences by role
```

### Step 2: Directory Structure Overview

```
frey-netcfg-mgmt/
├── README.md                          # Main documentation
├── .gitignore                         # Git ignore rules
├── ansible.cfg                        # Ansible configuration
├── requirements.txt                   # Python dependencies
│
├── playbooks/                         # Ansible playbooks
│   ├── backup_configs.yml             # Backup device configs
│   ├── generate_configs.yml           # Generate from templates
│   └── deploy_configs.yml             # Deploy to devices
│
├── templates/                         # Jinja2 templates
│   ├── arista_base.j2                 # Base configuration
│   ├── arista_interfaces.j2           # Interface configs
│   ├── arista_vlans.j2                # VLAN configs
│   ├── arista_vxlan.j2                # VXLAN/VTEP configs
│   ├── arista_bgp.j2                  # BGP and EVPN configs
│   └── arista_full_config.j2          # Complete config
│
├── configs/
│   ├── backup/                        # Configuration backups
│   └── generated/                     # Generated configs
│
├── group_vars/                        # Group variables
│   └── platforms_eos.yml              # EOS platform connection params
│   # all.yml is optional - can be omitted if all data in NetBox
│   # device_roles_*.yml only if needed for policy differences
│
├── host_vars/                         # Host-specific variables (rarely needed)
│
├── inventory/
│   └── hosts.yml                      # Local testing inventory
│
├── scripts/                           # Helper scripts
│   └── seed_netbox_from_clab.py       # Seed NetBox from containerlab
│
├── containerlab/
│   └── frey-lab.clab.yml              # Lab topology
│
└── docs/
    ├── AWX_SETUP.md                   # AWX configuration guide
    └── netbox_config_context.md       # NetBox data structure
```

---

## AWX Configuration

### Step 1: Create Project

1. Navigate to **Resources → Projects**
2. Click **Add**
3. Configure:
   - **Name**: `Frey Network Config Management`
   - **Organization**: Your organization
   - **Source Control Type**: `Git`
   - **Source Control URL**: `https://github.com/rbmacd/frey-netcfg-mgmt.git`
   - **Source Control Branch/Tag/Commit**: `main`
   - **Options**: Update Revision on Launch
   - **Options**: Clean (removes any local modifications)
4. Click **Save**

### Step 2: Verify NetBox Inventory

Your existing NetBox inventory should have:
- **Name**: `NetBox - Arista Devices`
- **Organization**: Your organization
- **Source**: NetBox (already configured)
- **Update Options**: Set to sync on launch or schedule

**Verify Groups Created**:
Navigate to the inventory and check that these groups exist:
- `device_roles_spine`
- `device_roles_leaf`
- `platforms_eos`
- `sites_<your_site_name>`

### Step 3: Create Credentials

#### Machine Credential (for Arista Devices)
1. Navigate to **Resources → Credentials**
2. Click **Add**
3. Configure:
   - **Name**: `Arista Device Credentials`
   - **Organization**: Your organization
   - **Credential Type**: `Machine`
   - **Username**: `admin`
   - **Password**: `<your_password>`
   - **Privilege Escalation Method**: `enable`
   - **Privilege Escalation Password**: `<enable_password>` (if different)
4. Click **Save**

#### Source Control Credential (if private repository)
1. Click **Add**
2. Configure:
   - **Name**: `Git Repository Credentials`
   - **Credential Type**: `Source Control`
   - **Username**: Your GitHub username
   - **Password/Token**: Personal access token
3. Click **Save**

### Step 4: Create Job Templates

#### Template 1: Backup Configurations

1. Navigate to **Resources → Templates**
2. Click **Add → Add job template**
3. Configure:
   - **Name**: `Backup - Arista Configs`
   - **Job Type**: `Run`
   - **Inventory**: `NetBox - Arista Devices`
   - **Project**: `Frey Network Config Management`
   - **Playbook**: `playbooks/backup_configs.yml`
   - **Credentials**: 
     - Select `Arista Device Credentials`
   - **Options**: 
     - Enable Fact Storage
     - Enable Concurrent Jobs
   - **Job Slicing**: 1 (or higher for parallel execution)
4. Click **Save**

#### Template 2: Generate Configurations

1. Click **Add → Add job template**
2. Configure:
   - **Name**: `Generate - Arista Configs`
   - **Job Type**: `Run`
   - **Inventory**: `NetBox - Arista Devices`
   - **Project**: `Frey Network Config Management`
   - **Playbook**: `playbooks/generate_configs.yml`
   - **Credentials**: 
     - Select `Arista Device Credentials`
   - **Options**: 
     - Enable Fact Storage
     - Prompt on Launch (Limit)
3. Click **Save**

#### Template 3: Deploy Configurations

1. Click **Add → Add job template**
2. Configure:
   - **Name**: `Deploy - Arista Configs`
   - **Job Type**: `Run`
   - **Inventory**: `NetBox - Arista Devices`
   - **Project**: `Frey Network Config Management`
   - **Playbook**: `playbooks/deploy_configs.yml`
   - **Credentials**: 
     - Select `Arista Device Credentials`
   - **Options**: 
     - Enable Fact Storage
     - Prompt on Launch (Limit)
     - Prompt on Launch (Verbosity)
4. Click **Save**

### Step 5: Create Workflow Template (Optional but Recommended)

1. Navigate to **Resources → Templates**
2. Click **Add → Add workflow template**
3. Configure:
   - **Name**: `Arista Config Management - Full Workflow`
   - **Organization**: Your organization
   - **Inventory**: `NetBox - Arista Devices`
4. Click **Save**
5. Click **Visualizer** to build workflow:

```
START
  │
  ├─→ Sync Project (update Git repo)
  │
  ├─→ Sync Inventory (update from NetBox)
  │
  ├─→ Backup Configurations
  │   │
  │   └─→ Generate Configurations (on success)
  │       │
  │       └─→ [APPROVAL NODE] (manual approval)
  │           │
  │           └─→ Deploy Configurations (on approval)
  │               │
  │               └─→ SUCCESS
```

**Workflow Steps**:
1. Add **Project Sync** node (update from Git)
2. Add **Inventory Sync** node (update from NetBox)
3. Add **Backup** job template (on success)
4. Add **Generate** job template (on success)
5. Add **Approval** node (manual gate before deploy)
6. Add **Deploy** job template (on approval)

### Step 6: Create Schedules

#### Daily Backup Schedule
1. Navigate to your **Backup** job template
2. Click **Schedules** tab
3. Click **Add**
4. Configure:
   - **Name**: `Daily Backup - 2 AM`
   - **Start Date/Time**: Tomorrow at 02:00
   - **Repeat Frequency**: Daily
   - **Time Zone**: Your timezone
5. Click **Save**

#### Weekly Generation Schedule
1. Navigate to your **Generate** job template
2. Click **Schedules** tab
3. Click **Add**
4. Configure:
   - **Name**: `Weekly Config Generation`
   - **Start Date/Time**: Next Sunday at 01:00
   - **Repeat Frequency**: Weekly (Sunday)
5. Click **Save**

---

## NetBox Integration

### Data Ownership and Separation of Concerns

**Understanding where data lives is critical to this architecture:**

| Data Type | Owner | Why | Example |
|-----------|-------|-----|---------|
| Device facts | **NetBox** | Source of truth for network state | Hostnames, IPs, interfaces |
| Network design | **NetBox** | Network architecture decisions | VLANs, subnets, BGP ASNs |
| Device config data | **NetBox** | Device-specific configuration | Interface descriptions, BGP neighbors |
| Organizational standards | **Git repo** | Corporate policy/standards | Banner text, default NTP/DNS |
| Templates | **Git repo** | How to render configs | Jinja2 templates |
| Automation logic | **Git repo** | How to execute changes | Ansible playbooks |
| Connection params | **Git repo** | How Ansible connects | ansible_network_os, become_method |
| Secrets | **AWX** | Secure credential storage | Passwords, API tokens |

### What Belongs in NetBox Config Context

Config context is JSON data in NetBox that becomes variables in Ansible. Put device-specific or site-specific data here:

**Use NetBox config context for:**
- VLANs and their assignments
- Interface configurations (IP addresses, descriptions, modes)
- Routing protocol configuration (BGP, OSPF)
- Device-specific NTP/DNS/Syslog servers
- ACLs and security policies
- QoS configurations
- Any data that varies per device or site

**Do not use NetBox config context for:**
- Organizational banner text (use group_vars)
- Default NTP servers that apply to all devices (use group_vars as default)
- Ansible connection parameters (use group_vars)
- Template logic (that belongs in Jinja2 templates)

### What Belongs in Git Group Variables

Group variables should contain ONLY Ansible connection parameters and (optionally) organizational metadata:

**Use group_vars for:**
- Ansible connection parameters (platforms_eos.yml)
- Organizational metadata (project name, contact info) - optional
- Documented organizational policies that differ by role (rare)

**Do not use group_vars for:**
- Network configuration data (NTP, DNS, syslog, etc.) - use NetBox
- "Default" or "fallback" values - use NetBox site/group config context
- Device-specific data - use NetBox
- IP addresses - use NetBox
- Interface configurations - use NetBox
- VLANs - use NetBox
- Routing configuration - use NetBox
- Any data that could vary by device or site - use NetBox

**Key Principle**: If you find yourself adding configuration data to group_vars, stop and ask: "Why isn't this in NetBox?"

### Variable Precedence and Override Behavior

When the same variable is defined in multiple places, Ansible uses this precedence (highest to lowest):

1. **AWX Extra Vars** (Job template extra_vars) - Highest priority
2. **NetBox Config Context** (Device or group-specific) - **Primary source**
3. **Git host_vars/** (Device-specific overrides)
4. **Git group_vars/** (Group-level defaults) - **Fallback defaults**
5. **Playbook vars**
6. **Role defaults** - Lowest priority

**Best Practice**: Use NetBox config context for all real data, use group_vars only for defaults/standards.

### Understanding AWX's NetBox Groups

AWX automatically creates inventory groups based on NetBox attributes:

| NetBox Attribute | AWX Group Name | Example |
|------------------|----------------|---------|
| Device Role | `device_roles_<role>` | `device_roles_spine` |
| Site | `sites_<site>` | `sites_dc1` |
| Platform | `platforms_<platform>` | `platforms_eos` |
| Tenant | `tenants_<tenant>` | `tenants_customer1` |
| Region | `regions_<region>` | `regions_us_east` |

### NetBox Config Context Structure

Config context is JSON data stored in NetBox that becomes available as variables in AWX. **This is where your actual device configuration data lives.**

**Location in NetBox**: `Devices → Config Contexts`

### VXLAN/EVPN Architecture Overview

This configuration supports a standard spine-leaf VXLAN/EVPN fabric architecture:

**Architecture Components:**
- **Spine Switches**: BGP route reflectors for EVPN overlay, IP fabric underlay
- **Leaf Switches**: VTEPs (VXLAN Tunnel Endpoints), EVPN clients, host connectivity
- **Underlay**: eBGP for IP connectivity between spines and leafs
- **Overlay**: EVPN (MP-BGP) for MAC/IP advertisement and VXLAN tunnel establishment

**Key Design Elements:**
- **ASN Strategy**: Unique ASN per leaf, shared ASN for spines
- **Loopbacks**: Loopback0 for BGP router-id, Loopback1 for VTEP source
- **VNI Mapping**: Standard VLAN-to-VNI mapping (VLAN 10 → VNI 10010)
- **Route Reflectors**: Spines act as EVPN route reflectors
- **ECMP**: Multiple paths between leafs via different spines

**Traffic Flow:**
1. East-West (L2): VXLAN encapsulation between leaf VTEPs
2. North-South: Leaf switches provide gateway functionality
3. Control Plane: EVPN distributes MAC/IP information via BGP

**Design Considerations:**

**ASN Assignment Strategy:**
- Option 1: Unique ASN per leaf (simplifies policy, recommended for scale)
- Option 2: Shared ASN for all spines, shared ASN for all leafs
- This template supports both models

**Loopback Addressing:**
- Loopback0: BGP router-id and overlay peering
- Loopback1: VTEP source address (leaf switches only)
- Use /32 addresses from dedicated ranges

**VNI Numbering:**
- Standard: VLAN + offset (VLAN 10 → VNI 10010)
- L3 VNI: Separate range (VNI 50000+)
- Maintain consistent mapping across fabric

**BGP Configuration:**
- Underlay: eBGP for simplicity and fast convergence
- Overlay: iBGP or eBGP EVPN sessions
- Route Reflectors: Spines provide RR functionality
- ECMP: Enable maximum-paths for load balancing

**Scalability Guidelines:**
- Spine count: Typically 2-4 for redundancy
- Leaf count: Limited by spine port density and RR scale
- VNI count: Arista supports 1000s of VNIs per device
- MAC table: Monitor MAC address table utilization

#### Example Device Config Context (spine01)

**This is the SOURCE OF TRUTH for device-specific configuration:**

```json
{
  "vlans": [
    {
      "vid": 10,
      "name": "DATA"
    },
    {
      "vid": 20,
      "name": "VOICE"
    },
    {
      "vid": 30,
      "name": "GUEST"
    },
    {
      "vid": 99,
      "name": "MANAGEMENT"
    }
  ],
  "interfaces": [
    {
      "name": "Ethernet1",
      "description": "To leaf01 - Ethernet1",
      "enabled": true,
      "mode": "routed",
      "ip_address": "10.0.1.1/30"
    },
    {
      "name": "Ethernet2",
      "description": "To leaf02 - Ethernet1",
      "enabled": true,
      "mode": "routed",
      "ip_address": "10.0.1.5/30"
    },
    {
      "name": "Ethernet3",
      "description": "To spine02 - iBGP peer link",
      "enabled": true,
      "mode": "routed",
      "ip_address": "10.0.0.1/30"
    }
  ],
  "bgp": {
    "asn": 65000,
    "router_id": "10.255.255.1",
    "router_id_loopback": {
      "id": 0,
      "ip": "10.255.255.1/32"
    },
    "maximum_paths": 4,
    "ecmp_paths": 4,
    "peer_groups": [
      {
        "name": "SPINE_UNDERLAY",
        "remote_as": "external",
        "ebgp_multihop": 3,
        "send_community": "extended"
      },
      {
        "name": "EVPN_OVERLAY",
        "remote_as": "external",
        "update_source": "Loopback0",
        "ebgp_multihop": 3,
        "send_community": "extended"
      }
    ],
    "neighbors": [
      {
        "ip": "10.0.1.2",
        "peer_group": "SPINE_UNDERLAY",
        "description": "leaf01 underlay"
      },
      {
        "ip": "10.0.1.6",
        "peer_group": "SPINE_UNDERLAY",
        "description": "leaf02 underlay"
      },
      {
        "ip": "10.255.255.11",
        "peer_group": "EVPN_OVERLAY",
        "description": "leaf01 EVPN"
      },
      {
        "ip": "10.255.255.12",
        "peer_group": "EVPN_OVERLAY",
        "description": "leaf02 EVPN"
      }
    ],
    "address_families": [
      {
        "afi": "ipv4",
        "safi": "unicast",
        "neighbors": [
          {
            "ip": "10.0.1.2"
          },
          {
            "ip": "10.0.1.6"
          }
        ]
      }
    ],
    "evpn": {
      "route_reflector_client": false,
      "neighbors": [
        {
          "ip": "10.255.255.11",
          "encapsulation": "vxlan"
        },
        {
          "ip": "10.255.255.12",
          "encapsulation": "vxlan"
        }
      ]
    }
  },
  "ntp_servers": [
    "10.0.0.100",
    "10.0.0.101"
  ],
  "dns_servers": [
    "10.0.0.50",
    "10.0.0.51"
  ],
  "syslog_servers": [
    "10.0.0.200"
  ]
}
```

#### Example Device Config Context (leaf01 - VTEP)

**Leaf switches are VTEPs (VXLAN Tunnel Endpoints):**

```json
{
  "vlans": [
    {
      "vid": 10,
      "name": "DATA"
    },
    {
      "vid": 20,
      "name": "VOICE"
    },
    {
      "vid": 30,
      "name": "GUEST"
    }
  ],
  "interfaces": [
    {
      "name": "Ethernet1",
      "description": "To spine01 - Uplink",
      "enabled": true,
      "mode": "routed",
      "ip_address": "10.0.1.2/30"
    },
    {
      "name": "Ethernet2",
      "description": "To spine02 - Uplink",
      "enabled": true,
      "mode": "routed",
      "ip_address": "10.0.1.10/30"
    },
    {
      "name": "Ethernet3",
      "description": "Server Port - VLAN 10",
      "enabled": true,
      "mode": "access",
      "vlan": 10
    },
    {
      "name": "Ethernet4",
      "description": "Trunk Port",
      "enabled": true,
      "mode": "trunk",
      "allowed_vlans": [10, 20, 30]
    }
  ],
  "vxlan": {
    "vtep_loopback": {
      "id": 1,
      "ip": "10.255.255.11/32"
    },
    "vtep_source_interface": "Loopback1",
    "udp_port": 4789,
    "vlan_vni_mappings": [
      {
        "vlan": 10,
        "vni": 10010
      },
      {
        "vlan": 20,
        "vni": 10020
      },
      {
        "vlan": 30,
        "vni": 10030
      }
    ]
  },
  "bgp": {
    "asn": 65001,
    "router_id": "10.255.255.11",
    "router_id_loopback": {
      "id": 0,
      "ip": "10.255.255.11/32"
    },
    "maximum_paths": 4,
    "ecmp_paths": 4,
    "peer_groups": [
      {
        "name": "LEAF_UNDERLAY",
        "remote_as": "external",
        "send_community": "extended"
      },
      {
        "name": "EVPN_OVERLAY",
        "remote_as": "external",
        "update_source": "Loopback0",
        "ebgp_multihop": 3,
        "send_community": "extended"
      }
    ],
    "neighbors": [
      {
        "ip": "10.0.1.1",
        "peer_group": "LEAF_UNDERLAY",
        "description": "spine01 underlay"
      },
      {
        "ip": "10.0.1.9",
        "peer_group": "LEAF_UNDERLAY",
        "description": "spine02 underlay"
      },
      {
        "ip": "10.255.255.1",
        "peer_group": "EVPN_OVERLAY",
        "description": "spine01 EVPN"
      },
      {
        "ip": "10.255.255.2",
        "peer_group": "EVPN_OVERLAY",
        "description": "spine02 EVPN"
      }
    ],
    "address_families": [
      {
        "afi": "ipv4",
        "safi": "unicast",
        "neighbors": [
          {
            "ip": "10.0.1.1"
          },
          {
            "ip": "10.0.1.9"
          }
        ],
        "networks": [
          {
            "prefix": "10.255.255.11/32"
          }
        ]
      }
    ],
    "evpn": {
      "route_reflector_client": false,
      "neighbors": [
        {
          "ip": "10.255.255.1",
          "encapsulation": "vxlan"
        },
        {
          "ip": "10.255.255.2",
          "encapsulation": "vxlan"
        }
      ]
    }
  },
  "ntp_servers": [
    "10.0.0.100",
    "10.0.0.101"
  ],
  "dns_servers": [
    "10.0.0.50",
    "10.0.0.51"
  ],
  "syslog_servers": [
    "10.0.0.200"
  ]
}
```

#### Example Site/Group Config Context (All DC1 Devices)

Create a config context with:
- **Name**: `DC1 Site Standards`
- **Weight**: 500 (lower than device-specific contexts)
- **Sites**: DC1
- **Data**:

```json
{
  "ntp_servers": [
    "10.1.0.100",
    "10.1.0.101"
  ],
  "dns_servers": [
    "10.1.0.50",
    "10.1.0.51"
  ],
  "syslog_servers": [
    "10.1.0.200"
  ],
  "snmp_location": "Data Center 1 - Building A",
  "timezone": "America/Chicago"
}
```

#### Example Role Config Context (All Spines)

Create a config context with:
- **Name**: `Spine Device Standards`
- **Weight**: 1000 (higher weight = higher priority)
- **Device Roles**: spine
- **Data**:

```json
{
  "logging_buffer_size": 100000,
  "tacacs_servers": [
    "10.0.0.150",
    "10.0.0.151"
  ]
}
```

### How NetBox Config Context Works with Templates

When the playbook runs, NetBox config context is automatically available. **All configuration data should come from NetBox**:

```jinja
{# In your Jinja2 template #}

{# Access data directly from NetBox config context #}
{% if netbox_config_context.vlans is defined %}
{% for vlan in netbox_config_context.vlans %}
vlan {{ vlan.vid }}
   name {{ vlan.name }}
{% endfor %}
{% endif %}

{# BGP configuration from NetBox #}
{% if netbox_config_context.bgp is defined %}
router bgp {{ netbox_config_context.bgp.asn }}
   router-id {{ netbox_config_context.bgp.router_id }}
{% endif %}

{# NTP servers from NetBox #}
{% if netbox_config_context.ntp_servers is defined %}
{% for ntp in netbox_config_context.ntp_servers %}
ntp server {{ ntp }}
{% endfor %}
{% endif %}
```

### Handling Missing NetBox Data

**Two approaches:**

#### Approach 1: Fail Loudly (Recommended)
Use playbook assertions to ensure required data exists in NetBox:

```yaml
- name: Validate required NetBox data
  ansible.builtin.assert:
    that:
      - netbox_config_context.ntp_servers is defined
      - netbox_config_context.dns_servers is defined
    fail_msg: "Missing required config context in NetBox"
```

#### Approach 2: Gracefully Skip (For Optional Features)
Use conditionals in templates to only render if data exists:

```jinja
{# Only configure SNMP if defined in NetBox #}
{% if netbox_config_context.snmp_community is defined %}
snmp-server community {{ netbox_config_context.snmp_community }} ro
{% endif %}
```

**Don't use "fallback defaults" in group_vars** - this hides missing data in NetBox and defeats the purpose of having a source of truth.

### Required NetBox Data

For the templates to work, ensure NetBox has these minimum requirements:

**Devices**:
- Name (becomes `inventory_hostname`)
- Device Role (spine, leaf, etc.)
- Platform (set to "eos" or "Arista EOS")
- Site
- Primary IP address

**Interfaces** (if using interface templates):
- Name
- Type
- Enabled status
- Description (optional)
- Mode (access/trunk/routed)

**IP Addresses**:
- Assigned to interfaces
- Set as primary IP

**VLANs** (if needed):
- VLAN ID
- Name
- Site assignment

**For VXLAN/EVPN Deployments (in Config Context)**:

**Required for all devices:**
- `bgp.asn` - BGP AS number
- `bgp.router_id` - BGP router ID
- `bgp.router_id_loopback` - Loopback interface for router ID
- `bgp.neighbors` - BGP neighbor definitions
- `bgp.address_families` - IPv4 unicast address family configuration

**Required for spine switches:**
- `bgp.evpn.neighbors` - EVPN overlay peers
- `bgp.peer_groups` - Underlay and overlay peer group definitions

**Required for leaf switches (VTEPs):**
- `vxlan.vtep_loopback` - Loopback interface for VTEP
- `vxlan.vtep_source_interface` - Source interface for VXLAN tunnels
- `vxlan.vlan_vni_mappings` - VLAN to VNI mappings
- `bgp.evpn.neighbors` - EVPN overlay peers (spine route reflectors)
- `vlans` - VLANs that will be extended via VXLAN

**Optional but recommended:**
- `bgp.maximum_paths` - ECMP path count
- `bgp.route_maps` - Route filtering policies
- `bgp.redistribute` - Route redistribution configuration

### Common Mistakes: Data Duplication and Misplaced Data

**INCORRECT - Defining network config data in group_vars:**
```yaml
# DO NOT DO THIS in group_vars/all.yml
dns_servers:
  - 8.8.8.8
  - 8.8.4.4
ntp_servers:
  - 0.pool.ntp.org
  - 1.pool.ntp.org
spine01_vlans:
  - vid: 10
    name: DATA
```
Explanation: This is network configuration data, not Ansible parameters. It belongs in NetBox, not Git.

**CORRECT - Use NetBox config context:**
```json
// In NetBox site config context for DC1
{
  "dns_servers": ["10.1.0.50", "10.1.0.51"],
  "ntp_servers": ["10.1.0.100", "10.1.0.101"]
}

// In NetBox device config context for spine01
{
  "vlans": [{"vid": 10, "name": "DATA"}]
}
```

**INCORRECT - Using "fallback defaults" in group_vars:**
```yaml
# DO NOT DO THIS - hides missing NetBox data
ntp_servers: "{{ netbox_config_context.ntp_servers | default(['0.pool.ntp.org']) }}"
```
Explanation: If NTP servers are missing from NetBox, you want to know about it, not silently use a fallback.

**CORRECT - Fail if required data missing:**
```yaml
# In playbook: Validate NetBox has required data
- name: Ensure NTP servers defined in NetBox
  assert:
    that: netbox_config_context.ntp_servers is defined
    fail_msg: "NTP servers not defined in NetBox for {{ inventory_hostname }}"
```

**INCORRECT - Mixing NetBox and group_vars for same data:**
```yaml
# In group_vars
dns_servers:
  - 8.8.8.8

# In NetBox config context
{
  "dns_servers": ["10.0.0.50"]
}
```
Explanation: Creates confusion about which source is authoritative and leads to inconsistency.

**CORRECT - NetBox is the ONLY source:**
```json
// ALL DNS configuration in NetBox config context
{
  "dns_servers": ["10.0.0.50", "10.0.0.51"]
}
```
```yaml
# group_vars/all.yml - empty or omitted entirely
---
# This file intentionally left empty
# All configuration data in NetBox
```

### How to Structure Your Data

**Decision tree for where to put data:**

```
Is this network configuration data (IPs, VLANs, DNS, NTP, routing, etc.)?
├─ YES → Put in NetBox config context (device, site, or role-based)
│
└─ NO → Is this an Ansible connection parameter?
    ├─ YES → Put in Git group_vars/platforms_eos.yml
    │
    └─ NO → Is this how to render configs (template logic)?
        ├─ YES → Put in Git templates/
        │
        └─ NO → Is this automation logic (when/how to execute)?
            ├─ YES → Put in Git playbooks/
            │
            └─ NO → Is this a genuine organizational POLICY that differs by role?
                ├─ YES → Put in Git group_vars/device_roles_*.yml
                │
                └─ NO → Is this a secret/password?
                    ├─ YES → Put in AWX credentials
                    │
                    └─ NO → Is this just organizational metadata?
                        └─ YES → Optionally put in Git group_vars/all.yml
```

**Simplified Rule**: 
- Network data → NetBox
- Connection params → group_vars/platforms_eos.yml
- Everything else → Templates or playbooks
- Secrets → AWX

---

## Testing & Validation

### Local Testing (Without AWX)

#### Test 1: Verify Repository Structure

```bash
# Clone your repository
git clone https://github.com/yourusername/frey-netcfg-mgmt.git
cd frey-netcfg-mgmt

# Install dependencies
pip install -r requirements.txt
ansible-galaxy collection install arista.eos netbox.netbox

# Verify Ansible can see inventory
ansible-inventory --list -i inventory/hosts.yml

# Check playbook syntax
ansible-playbook playbooks/generate_configs.yml --syntax-check
```

#### Test 2: Generate Configs Locally

```bash
# Generate configs using static inventory
ansible-playbook playbooks/generate_configs.yml -i inventory/hosts.yml

# Check generated config
cat configs/generated/spine01.cfg
```

### End-to-End Testing with NetBox and Containerlab

**Purpose**: Test the complete production workflow (Containerlab → NetBox → AWX → Devices) in a safe lab environment.

This workflow mirrors production exactly:
1. Infrastructure defined in containerlab YAML
2. NetBox seeded from containerlab topology
3. AWX syncs inventory from NetBox
4. AWX generates configs from NetBox data
5. AWX deploys to containerlab devices (via SSH, same as production)

**Prerequisites**:
- Containerlab installed
- NetBox instance accessible
- AWX with NetBox dynamic inventory configured
- Python 3.8+ with required packages

#### Step 1: Seed NetBox from Containerlab

The `seed_netbox_from_clab.py` script automates NetBox population:

```bash
# Set environment variables
export NETBOX_URL=https://netbox.example.com
export NETBOX_APITOKEN=your_token_here

# Run seeding script
python scripts/seed_netbox_from_clab.py containerlab/frey-lab.clab.yml
```

**What the script creates in NetBox**:
- **Devices**: spine01, spine02, leaf01, leaf02
- **Device Roles**: Spine, Leaf (auto-detected from hostname)
- **Platform**: Arista EOS
- **Site**: frey-netcfg-lab (from containerlab name)
- **Interfaces**: Management1, eth1, eth2, etc.
- **Links**: Cables between devices per topology
- **Management IPs**: 172.20.20.2-5 (primary IPs)
- **Config Context**: Complete BGP/EVPN/VXLAN configuration
  - Spines: BGP route reflectors with EVPN overlay
  - Leafs: VTEP configuration with VXLAN, VLANs, VNI mappings
  - Auto-generated BGP neighbors from topology
  - Router IDs: 10.255.255.1 (spine01), 10.255.255.11 (leaf01), etc.
  - ASNs: 65000 (spines), 65001+ (leafs)

**Script Options**:
```bash
# Disable SSL verification (for self-signed certs)
python scripts/seed_netbox_from_clab.py --no-ssl-verify containerlab/frey-lab.clab.yml

# Skip config context generation (infrastructure only)
python scripts/seed_netbox_from_clab.py --skip-config-context containerlab/frey-lab.clab.yml
```

#### Step 2: Deploy Containerlab

Deploy the lab with minimal bootstrap configuration:

```bash
cd containerlab
sudo containerlab deploy -t frey-lab.clab.yml
```

**Devices boot with**:
- Factory default configuration
- Management IP configured automatically
- SSH enabled (cEOS default)
- No routing, VLANs, or BGP configured

**Verify containerlab deployment**:
```bash
# Check running containers
sudo containerlab inspect -t frey-lab.clab.yml

# Test SSH access
ssh admin@172.20.20.2  # Default password: admin

# Verify minimal config
show running-config
```

#### Step 3: Sync AWX Inventory from NetBox

In AWX, your NetBox dynamic inventory automatically discovers the new devices:

**Option A - Automatic Sync**:
- If "Update on Launch" is enabled, inventory syncs when jobs run

**Option B - Manual Sync**:
1. Navigate to **Resources → Inventories**
2. Select your NetBox inventory
3. Click **Sync** button
4. Wait for completion

**Verify devices appear**:
- Go to **Hosts** tab
- Confirm: spine01, spine02, leaf01, leaf02
- Go to **Groups** tab
- Confirm: device_roles_spine, device_roles_leaf, platforms_eos, sites_frey_netcfg_lab

#### Step 4: Generate Configurations in AWX

Run the configuration generation job:

1. Navigate to **Resources → Templates**
2. Select `Generate - Arista Configs`
3. Click **Launch**
4. Set **Limit**: `sites_frey_netcfg_lab` (targets only containerlab devices)
5. Click **Next** → **Launch**

**What happens**:
- AWX reads NetBox config context (BGP, VXLAN, VLANs)
- Jinja2 templates render complete configurations
- Configs include full EVPN/VXLAN fabric configuration
- Files saved in AWX artifacts

**Review generated configs**:
- Check AWX job output
- Download artifacts to review configurations

#### Step 5: Deploy to Containerlab (Check Mode First)

Test deployment without making changes:

1. Select `Deploy - Arista Configs`
2. Click **Launch**
3. Set **Limit**: `sites_frey_netcfg_lab`
4. Enable **Check Mode** (dry run)
5. Click **Next** → **Launch**

**Review the output** - what would change on each device.

#### Step 6: Deploy to Containerlab (Live)

Deploy the full configuration:

1. Select `Deploy - Arista Configs`
2. Click **Launch**
3. Set **Limit**: `sites_frey_netcfg_lab`
4. **Do NOT** enable Check Mode
5. Click **Next** → **Launch**

**What happens**:
- AWX connects via SSH to 172.20.20.2-5
- Uses `arista.eos.eos_config` module
- Pushes complete BGP/EVPN/VXLAN configuration
- Devices now have full production-like config

#### Step 7: Verify VXLAN/EVPN Fabric

SSH to devices and verify the deployment:

```bash
# Connect to spine
ssh admin@172.20.20.2

# Verify BGP underlay
show ip bgp summary
show ip route bgp

# Verify EVPN overlay
show bgp evpn summary
show bgp evpn

# On leaf switches
ssh admin@172.20.20.4

# Verify VXLAN
show vxlan vtep
show vxlan vni
show vxlan address-table

# Verify VLANs
show vlan

# Check interfaces
show ip interface brief
```

### Complete Workflow Summary

```
┌─────────────────────────────────────────────────────────────┐
│  1. Create/Update containerlab/frey-lab.clab.yml           │
│     (defines nodes and links only)                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Run seed_netbox_from_clab.py                            │
│     Creates devices, interfaces, links, config context      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Deploy containerlab                                     │
│     Devices boot with factory defaults                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  4. AWX syncs inventory from NetBox                         │
│     Discovers devices automatically                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  5. AWX generates configs from NetBox data                  │
│     Templates + Config Context = Full Configuration         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  6. AWX deploys to containerlab devices                     │
│     Same SSH-based deployment as production                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  7. Verify EVPN/VXLAN fabric is operational                │
│     Full production-like network in containerlab            │
└─────────────────────────────────────────────────────────────┘
```

**Key Benefits**:
- **Identical to Production**: Same NetBox → AWX → Device workflow
- **Safe Testing**: Containerlab environment, not production
- **Full Automation**: Single YAML file → Complete fabric
- **Config Context Testing**: Validates templates against real NetBox data
- **Rapid Iteration**: Destroy and rebuild in minutes

#### Cleanup

When finished testing:

```bash
# Destroy containerlab
cd containerlab
sudo containerlab destroy -t frey-lab.clab.yml

# Optional: Clean up NetBox
# (manually delete devices/site or use NetBox UI)
```

### Test 3: Containerlab Testing (Legacy Local Method)

**Note**: This method is deprecated in favor of the NetBox-driven workflow above.

For quick local testing without NetBox/AWX:

```bash
# Generate configs locally first
ansible-playbook playbooks/generate_configs.yml -i inventory/hosts.yml

# Then deploy containerlab with pre-generated configs
# (Requires updating clab YAML to reference startup-config files)
cd containerlab
sudo containerlab deploy -t frey-lab.clab.yml
```

This approach bypasses NetBox/AWX and loads configs directly from files.

### containerlab/frey-lab.clab.yml

**Note**: This topology file contains NO configuration - devices boot with factory defaults. The `seed_netbox_from_clab.py` script reads this file to populate NetBox, then AWX deploys full configurations.

**Why this approach:**
- Containerlab defines only infrastructure (nodes and links)
- NetBox becomes the source of truth (seeded from containerlab)
- AWX deploys configurations (same workflow as production)
- Tests the complete end-to-end automation pipeline

### AWX Testing

#### Test 1: Verify Inventory Sync

1. Navigate to **Resources → Inventories**
2. Select `NetBox - Arista Devices`
3. Click **Sync** button (or **Sources** tab → sync icon)
4. Wait for sync to complete
5. Click **Hosts** tab - verify devices appear
6. Click **Groups** tab - verify groups created

#### Test 2: Test Single Device

1. Navigate to **Resources → Templates**
2. Select `Generate - Arista Configs`
3. Click **Launch**
4. In **Limit** field, enter: `spine01`
5. Click **Next** → **Launch**
6. Monitor job output
7. Check AWX artifacts for generated config

#### Test 3: Dry Run (Check Mode)

1. Select `Deploy - Arista Configs`
2. Click **Launch**
3. In **Limit** field, enter: `spine01`
4. Enable **Check Mode**
5. Click **Next** → **Launch**
6. Review what WOULD change (no actual changes made)

#### Test 4: Full Workflow

1. Navigate to your workflow template
2. Click **Launch**
3. Monitor each step in visualizer
4. At approval node, review generated configs
5. Approve or deny deployment

### Validating VXLAN/EVPN Configuration

After deploying configurations to devices, validate the VXLAN/EVPN fabric:

#### Underlay Validation

```bash
# SSH to spine or leaf
ssh admin@spine01

# Verify BGP underlay sessions
show ip bgp summary

# Check IP connectivity to all loopbacks
ping 10.255.255.11 source 10.255.255.1

# Verify routing table
show ip route bgp
```

#### Overlay Validation

```bash
# Verify EVPN BGP sessions
show bgp evpn summary

# Check EVPN routes
show bgp evpn

# Verify learned MAC addresses
show bgp evpn route-type mac-ip

# Check VXLAN tunnel status (on leaf switches)
show vxlan vtep
show vxlan vni
show vxlan address-table

# Verify VXLAN interface
show interfaces vxlan1
```

#### End-to-End Validation

```bash
# On leaf switch - verify MAC learning
show mac address-table

# Verify VLAN to VNI mapping
show vxlan config-sanity

# Check EVPN control plane
show bgp evpn instance

# Verify VTEP flood lists
show vxlan flood vtep
```

**Common Issues to Check:**
- BGP sessions not established: Check IP connectivity, ASN configuration
- EVPN routes not received: Verify send-community extended is configured
- VXLAN tunnels down: Check VTEP loopback reachability
- MAC addresses not learned: Verify VLAN-VNI mappings are correct
- No traffic flow: Check flood VTEP lists or validate VXLAN encapsulation

---

## Workflow

### Standard Operating Procedure

**Note**: For end-to-end testing with containerlab, see [Testing & Validation](#testing--validation) section for the complete NetBox-driven workflow.

#### 1. Update NetBox (Source of Truth)

```
Actions in NetBox:
├── Add new device
├── Modify interface configuration
├── Update IP addresses
├── Change VLAN assignments
├── Update config context (BGP, VLANs, etc.)
└── Document changes in device comments
```

#### 2. Sync AWX Inventory

**Option A - Automatic**: 
- Scheduled sync runs every hour
- Project sync on launch enabled

**Option B - Manual**:
1. Go to NetBox inventory in AWX
2. Click sync button
3. Wait for completion

#### 3. Generate Configurations

**Option A - Via Workflow**:
- Run full workflow template
- Automatically syncs, backs up, generates

**Option B - Individual Job**:
1. Run `Generate - Arista Configs` job
2. Use **Limit** for specific devices/groups:
   - Single device: `spine01`
   - Group: `device_roles_spine`
   - Multiple: `spine01,leaf01`
   - Pattern: `spine*`

#### 4. Review Generated Configs

1. Navigate to job output in AWX
2. Check artifacts directory (if configured)
3. Review configs in Git repository
4. Compare against backup if making changes

#### 5. Test in Lab (Optional)

```bash
# Update configs in repo
git pull

# Deploy to Containerlab
cd containerlab
sudo containerlab deploy -t frey-lab.clab.yml

# Test configuration
ssh admin@172.20.20.2
show running-config
```

#### 6. Backup Production

Run `Backup - Arista Configs` job template:
- Backs up current running configs
- Timestamped files in configs/backup/
- Safety net before changes

#### 7. Deploy to Production

**Using Check Mode First**:
1. Run `Deploy - Arista Configs`
2. Enable **Check Mode**
3. Review planned changes
4. If good, run again without check mode

**Using Workflow**:
- Approval node provides manual gate
- Review before approving
- Deploy happens automatically after approval

**Limiting Deployment**:
```
# Examples of limit patterns
spine01                    # Single device
device_roles_spine         # All spines
sites_dc1                  # All devices in DC1
spine01,spine02            # Multiple specific devices
leaf*                      # Pattern match
```

#### 8. Verify Deployment

1. Check AWX job output for errors
2. Verify device connectivity
3. Spot-check critical services
4. Review syslog for issues

---

## Troubleshooting

### AWX Issues

#### Problem: AWX doesn't see my Git changes

**Solution**:
```
1. Check project configuration
2. Ensure "Update Revision on Launch" is enabled
3. Manually sync project: Resources → Projects → Sync
4. Verify Git URL and credentials
5. Check AWX can reach Git repository
```

#### Problem: NetBox inventory not syncing

**Solution**:
```
1. Verify NetBox API is accessible from AWX
2. Check NetBox token has correct permissions
3. Review AWX inventory source configuration
4. Check AWX logs: /var/log/tower/
5. Test NetBox API manually:
   curl -H "Authorization: Token YOUR_TOKEN" \
        https://netbox.example.com/api/dcim/devices/
```

#### Problem: Variables not being applied

**Solution**:
```
1. Check if data is in NetBox config context (should be primary source)
2. Verify NetBox config context JSON is valid
3. Check AWX inventory sync completed successfully
4. Review variable precedence - NetBox overrides group_vars
5. Don't duplicate data in both NetBox and group_vars
6. Add debug task to see what variables AWX provides:
   - debug: var=netbox_config_context
7. Verify group_vars file names match AWX group names exactly
```

#### Problem: Data inconsistency between devices

**Solution**:
```
1. Verify you're not storing device data in group_vars (anti-pattern)
2. Check NetBox config context for each device
3. Ensure AWX inventory sync is recent
4. Review config context weights (higher = priority)
5. Don't hardcode device-specific values in templates
6. Use NetBox as single source of truth
```

### Template Issues

#### Problem: Jinja2 template errors

**Solution**:
```
1. Check template syntax locally:
   ansible-playbook playbooks/generate_configs.yml --syntax-check
2. Add debug tasks to print variable values
3. Verify variable exists and has correct structure
4. Use default filters: {{ var | default('fallback') }}
5. Check for undefined variables in template
```

#### Problem: Generated configs are incomplete

**Solution**:
```
1. Verify NetBox has all required data
2. Check NetBox config context structure
3. Review playbook output for warnings
4. Add conditionals in templates for optional data
5. Validate template logic with test data
```

### Connectivity Issues

#### Problem: Cannot connect to devices

**Solution**:
```
1. Verify AWX can reach device management IPs
2. Check firewall rules
3. Verify credentials in AWX
4. Test manual SSH from AWX container:
   ssh admin@device-ip
5. Check device has SSH enabled and accessible
```

#### Problem: Privilege escalation fails

**Solution**:
```
1. Verify enable password in credentials
2. Check privilege escalation method set to "enable"
3. Test enable manually on device
4. Review device AAA configuration
5. Check for enable secret vs enable password
```

### NetBox Data Issues

#### Problem: Devices not appearing in AWX inventory

**Solution**:
```
1. Verify device has primary IP in NetBox
2. Check device status is "Active"
3. Review inventory source filters in AWX
4. Ensure device has correct platform/role
5. Check NetBox API returns the device:
   GET /api/dcim/devices/?name=spine01
```

#### Problem: Config context not available in playbook

**Solution**:
```
1. Verify config context is assigned in NetBox
2. Check config context weight (higher = priority)
3. Ensure inventory sync completed after changes
4. Review netbox_config_context variable in job
5. Validate JSON syntax in NetBox config context
```

---

## Best Practices

### Data Management Principles

**Recommended practices:**
- NetBox is the ONLY source of truth for network data - No exceptions
- Keep group_vars/ minimal - ideally just platforms_eos.yml
- Fail loudly (with assertions) if required NetBox data is missing
- Use NetBox config context for ALL network configuration data
- Keep templates focused on rendering, not business logic
- Document required NetBox config context structure
- Validate NetBox data in playbooks before generating configs

**Practices to avoid:**
- Putting ANY network configuration data in group_vars (DNS, NTP, VLANs, etc.)
- Using "fallback defaults" - they hide missing NetBox data
- Duplicating data between NetBox and Git
- Overriding NetBox data with static values in Git
- Storing the same data in multiple places
- Using group_vars/all.yml for configuration data

### NetBox Management

**Recommended practices:**
- Use config contexts for device-specific data
- Set appropriate weights (1000 = default, higher = override)
- Document changes in device comments
- Use consistent naming conventions
- Assign devices to proper roles and sites
- Keep primary IPs updated

**Practices to avoid:**
- Storing passwords in config context
- Using invalid JSON in config context
- Leaving devices without primary IPs
- Creating circular dependencies in config context
- Duplicating data between Git and NetBox

### Template Development

**Recommended practices:**
- Use default filters for optional variables
- Add comments explaining complex logic
- Keep templates modular and reusable
- Test with minimal data first
- Version control all templates
- Use meaningful variable names

**Practices to avoid:**
- Hardcoding values that should be in NetBox
- Creating overly complex nested loops
- Assuming all variables exist
- Mixing business logic in templates
- Skipping input validation

### Git Repository Management

**Recommended practices:**
- Keep repository structure minimal
- Only create group_vars files when genuinely needed
- Handle simple role variations in templates, not separate group_vars
- Use meaningful commit messages
- Create branches for major changes
- Tag releases (v1.0.0, v1.1.0)
- Document changes in commits
- Review changes before committing
- Keep sensitive data out of repo

**Practices to avoid:**
- Creating device_roles_*.yml files "just in case"
- Committing passwords or tokens
- Pushing directly to main (use PRs)
- Making untested changes
- Ignoring .gitignore rules
- Storing backup configs in Git
- Proliferating group_vars files unnecessarily

### AWX Job Execution

**Recommended practices:**
- Use check mode before deploying
- Backup before making changes
- Use limits for testing
- Schedule regular backups
- Enable fact caching
- Use workflows for complex tasks

**Practices to avoid:**
- Deploying to all devices without testing
- Skipping backups
- Running jobs without reviewing output
- Disabling approval gates in production
- Ignoring failed job notifications

---

## Quick Reference

### Common AWX Limit Patterns

```bash
# Single device
spine01

# Device role group
device_roles_spine

# Site group
sites_dc1

# Platform group
platforms_eos

# Multiple devices
spine01,spine02,leaf01

# Pattern matching
spine*
leaf0[1-2]

# Boolean operators
device_roles_spine:&sites_dc1    # AND
device_roles_spine:!sites_dc2    # NOT

# Complex patterns
device_roles_spine:&sites_dc1:!spine01
```

### Useful Ansible Commands (Local)

```bash
# List inventory
ansible-inventory --list -i inventory/hosts.yml

# Test connectivity
ansible all -m ping -i inventory/hosts.yml

# Check syntax
ansible-playbook playbooks/generate_configs.yml --syntax-check

# Dry run
ansible-playbook playbooks/generate_configs.yml --check

# Run with limit
ansible-playbook playbooks/generate_configs.yml --limit spine01

# Verbose output
ansible-playbook playbooks/generate_configs.yml -vvv
```

### AWX API Examples

```bash
# Get job templates
curl -X GET https://awx.example.com/api/v2/job_templates/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# Launch job
curl -X POST https://awx.example.com/api/v2/job_templates/123/launch/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"limit": "spine01"}'

# Get job status
curl -X GET https://awx.example.com/api/v2/jobs/456/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### VXLAN/EVPN Verification Commands

```bash
# Underlay verification
show ip bgp summary
show ip route bgp
show ip interface brief

# Overlay verification
show bgp evpn summary
show bgp evpn
show bgp evpn route-type mac-ip
show bgp evpn instance

# VXLAN verification (leaf switches)
show vxlan vtep
show vxlan vni
show vxlan address-table
show vxlan config-sanity
show interfaces vxlan1

# Control plane verification
show bgp evpn route-type imet
show mac address-table dynamic

# Troubleshooting
show logging | include BGP|EVPN|VXLAN
show running-config section bgp
show running-config section vxlan
```

---

## Next Steps

### Immediate Actions

1. Clone and set up repository structure
2. Install Python dependencies and Ansible collections
3. Set up containerlab environment with cEOS image
4. Configure NetBox instance (or use existing)
5. Configure AWX with NetBox dynamic inventory
6. Test end-to-end workflow:
   - Seed NetBox from containerlab YAML
   - Deploy containerlab with factory defaults
   - AWX generates and deploys configs
7. Verify VXLAN/EVPN fabric operation

### Short Term Enhancements

- Add more device roles (border, access, etc.)
- Expand VXLAN/EVPN capabilities:
  - L3 VNI support (symmetric IRB)
  - Anycast gateway configuration
  - Multi-tenancy with VRFs
  - EVPN multi-homing (ESI/LAG)
- Create templates for additional features:
  - MLAG configuration
  - ACLs and security policies
  - QoS policies
  - Multicast for BUM traffic
- Implement approval workflows
- Add Slack/Teams notifications
- Create dashboards for monitoring

### Long Term Goals

- Integrate with CI/CD pipeline
- Add automated testing (molecule, pytest)
- Implement drift detection
- Create compliance checking
- Build self-service portal
- Expand to multi-vendor support

---

## Additional Resources

### Documentation Links

- **Ansible EOS Collection**: https://docs.ansible.com/ansible/latest/collections/arista/eos/
- **NetBox Ansible Collection**: https://docs.ansible.com/ansible/latest/collections/netbox/netbox/
- **AWX Documentation**: https://ansible.readthedocs.io/projects/awx/
- **NetBox Documentation**: https://docs.netbox.dev/
- **Jinja2 Documentation**: https://jinja.palletsprojects.com/
- **Containerlab**: https://containerlab.dev/

### Example NetBox Queries

```python
# Get all spine devices
/api/dcim/devices/?role=spine

# Get device with interfaces
/api/dcim/devices/?name=spine01&include=interfaces

# Get config context for device
/api/dcim/devices/123/render-config/

# Get all VLANs
/api/ipam/vlans/
```

---

## Support and Contribution

### Getting Help

1. Check AWX job logs for errors
2. Review this documentation
3. Test locally with static inventory
4. Validate NetBox data structure
5. Check Ansible verbose output (-vvv)

### Contributing

1. Fork the repository
2. Create feature branch
3. Test changes thoroughly
4. Update documentation
5. Submit pull request

---

**Project**: Frey Network Config Management  
**Author**: Rob MacDonald

---

## Critical Reminders

### Architecture Summary

This system follows a strict **separation of concerns**:

1. **NetBox = Source of Truth**
   - All device-specific data (IPs, interfaces, VLANs, BGP, etc.)
   - Site and device-specific configurations
   - Network state and design decisions

2. **Git = Configuration Logic**
   - Jinja2 templates (HOW to render configs)
   - Ansible playbooks (HOW to execute automation)
   - Organizational defaults (fallback values only)
   - Standards and policies (banner text, etc.)

3. **AWX = Execution Engine**
   - Pulls inventory from NetBox (no static inventory)
   - Executes playbooks from Git
   - Manages credentials securely
   - Orchestrates workflows

**Golden Rule**: If it's data about a specific device, site, or network design, it belongs in NetBox—not in Git. Git contains only templates, logic, and Ansible connection parameters.

### The group_vars/ Folder

For pure NetBox implementations, you only need ONE file:
- `group_vars/platforms_eos.yml` - Contains ONLY Ansible connection parameters

You do NOT need:
- `group_vars/all.yml` - Can be omitted entirely; all config data in NetBox
- `group_vars/device_roles_*.yml` - Only create for genuine policy differences (rare)
- `host_vars/` - Never needed; use NetBox config context instead

If you find yourself adding configuration data to group_vars, STOP - that data belongs in NetBox config context.