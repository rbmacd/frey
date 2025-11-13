#!/usr/bin/env python3
"""
ContainerLab to NetBox Synchronization Script
Reads a clab.yml file and populates NetBox with devices, interfaces, and IPs
"""

import yaml
import pynetbox
import sys
import os
import re
import logging
import argparse
import urllib3
from ipaddress import ip_interface
from pynetbox.core.query import RequestError
from urllib3.exceptions import InsecureRequestWarning

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clab_netbox_sync.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Device type mapping for ContainerLab kinds
DEVICE_TYPE_MAP = {
    'ceos': 'Arista cEOS',
    'linux': 'Linux Host',
    'alpine': 'Alpine Linux'
}

MANUFACTURER_MAP = {
    'ceos': 'Arista',
    'linux': 'Generic',
    'alpine': 'Alpine'
}

# Ansible network_os mapping for different device kinds/manufacturers
ANSIBLE_NETWORK_OS_MAP = {
    'ceos': 'eos',
    'linux': 'linux',
    'alpine': 'linux',
    'vr-sros': 'sros',
    'vr-vmx': 'junos',
    'vr-xrv9k': 'iosxr',
    'vr-veos': 'eos',
    'crpd': 'junos',
    'vr-csr': 'ios',
    'vr-n9kv': 'nxos',
    'vr-vqfx': 'junos',
    'sonic-vs': 'sonic'
}

# Additional mapping by manufacturer name (fallback)
MANUFACTURER_TO_ANSIBLE_OS = {
    'Arista': 'eos',
    'Cisco': 'ios',
    'Juniper': 'junos',
    'Nokia': 'sros',
    'Generic': 'linux',
    'Alpine': 'linux'
}

# Config Context Constants
LOOPBACK_BASE = "10.255.255."
VTEP_LOOPBACK_BASE = "10.255.254."  # Different range for VTEP
SPINE_LOOPBACK_START = 1
LEAF_LOOPBACK_START = 101
BASE_ASN_SPINE = 65000
BASE_ASN_LEAF = 65100

# P2P Link addressing
P2P_LINK_BASE = "10.0."  # Will be 10.0.{link_index}.{0,1}/31

# Default VLANs for leaf switches
DEFAULT_VLANS = [
    {"vid": 10, "name": "VLAN10"},
    {"vid": 20, "name": "VLAN20"},
    {"vid": 30, "name": "VLAN30"}
]

def load_clab_yaml(filepath):
    """Load and parse the ContainerLab YAML file"""
    try:
        with open(filepath, 'r') as f:
            data = yaml.safe_load(f)
            logger.info(f"Successfully loaded ContainerLab file: {filepath}")
            return data
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading file: {e}")
        raise

def get_or_create_manufacturer(nb, name):
    """Get or create a manufacturer in NetBox"""
    try:
        manufacturer = nb.dcim.manufacturers.get(name=name)
        if not manufacturer:
            logger.info(f"Creating manufacturer: {name}")
            manufacturer = nb.dcim.manufacturers.create(name=name, slug=name.lower())
        else:
            logger.debug(f"Manufacturer already exists: {name}")
        return manufacturer
    except RequestError as e:
        logger.error(f"NetBox API error creating manufacturer {name}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error with manufacturer {name}: {e}")
        raise

def get_or_create_device_type(nb, kind, manufacturer_id):
    """Get or create a device type in NetBox"""
    try:
        device_type_name = DEVICE_TYPE_MAP.get(kind, kind)
        device_type = nb.dcim.device_types.get(model=device_type_name)
        
        if not device_type:
            logger.info(f"Creating device type: {device_type_name}")
            device_type = nb.dcim.device_types.create(
                manufacturer=manufacturer_id,
                model=device_type_name,
                slug=device_type_name.lower().replace(' ', '-')
            )
        else:
            logger.debug(f"Device type already exists: {device_type_name}")
        return device_type
    except RequestError as e:
        logger.error(f"NetBox API error creating device type {device_type_name}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error with device type {device_type_name}: {e}")
        raise

def get_or_create_site(nb, name):
    """Get or create a site in NetBox using the clab name"""
    try:
        site = nb.dcim.sites.get(name=name)
        if not site:
            logger.info(f"Creating site: {name}")
            site = nb.dcim.sites.create(
                name=name,
                slug=name.lower().replace(' ', '-')
            )
        else:
            logger.debug(f"Site already exists: {name}")
        return site
    except RequestError as e:
        logger.error(f"NetBox API error creating site {name}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error with site {name}: {e}")
        raise

def get_or_create_device_role(nb, role_name):
    """Get or create a device role"""
    try:
        role = nb.dcim.device_roles.get(name=role_name)
        if not role:
            logger.info(f"Creating device role: {role_name}")
            role = nb.dcim.device_roles.create(
                name=role_name,
                slug=role_name.lower().replace(' ', '-'),
                color='2196f3'  # Blue color
            )
        else:
            logger.debug(f"Device role already exists: {role_name}")
        return role
    except RequestError as e:
        logger.error(f"NetBox API error creating device role {role_name}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error with device role {role_name}: {e}")
        raise

def get_ansible_network_os(kind, manufacturer_name):
    """
    Determine the appropriate ansible_network_os value based on device kind and manufacturer
    """
    # First try to map directly from the ContainerLab kind
    ansible_os = ANSIBLE_NETWORK_OS_MAP.get(kind)
    
    # If not found, try to map from manufacturer
    if not ansible_os:
        ansible_os = MANUFACTURER_TO_ANSIBLE_OS.get(manufacturer_name, 'linux')
    
    logger.debug(f"Mapped kind '{kind}' / manufacturer '{manufacturer_name}' to ansible_network_os: {ansible_os}")
    return ansible_os

def ensure_custom_field_exists(nb):
    """
    Ensure the ansible_network_os custom field exists in NetBox.
    Create it if it doesn't exist.
    """
    try:
        # Check if custom field exists
        custom_field = nb.extras.custom_fields.get(name='ansible_network_os')
        
        if not custom_field:
            logger.info("Creating custom field: ansible_network_os")
            custom_field = nb.extras.custom_fields.create(
                name='ansible_network_os',
                object_types=['dcim.device'],
                type='text',
                description='Ansible network OS type for dynamic inventory',
                weight=100
            )
            logger.info("Successfully created ansible_network_os custom field")
        else:
            logger.debug("Custom field ansible_network_os already exists")
        
        return custom_field
    except RequestError as e:
        logger.error(f"NetBox API error creating custom field: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error ensuring custom field exists: {e}")
        raise

def set_device_custom_fields(nb, device, ansible_network_os):
    """
    Set custom fields for a device, including ansible_network_os
    """
    try:
        # Update device with custom field data
        logger.info(f"Setting ansible_network_os='{ansible_network_os}' for device {device.name}")
        device.custom_fields = {'ansible_network_os': ansible_network_os}
        device.save()
        logger.debug(f"Successfully set custom fields for {device.name}")
    except RequestError as e:
        logger.error(f"NetBox API error setting custom fields for {device.name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error setting custom fields for {device.name}: {e}")

def determine_device_role(device_name):
    """Determine device role from hostname"""
    device_lower = device_name.lower()
    if device_lower.startswith('spine'):
        return 'spine'
    elif device_lower.startswith('leaf'):
        return 'leaf'
    elif device_lower.startswith('border'):
        return 'border'
    else:
        return 'unknown'

def extract_device_number(device_name):
    """Extract numeric suffix from device name (e.g., spine01 -> 1)"""
    match = re.search(r'(\d+)$', device_name)
    if match:
        return int(match.group(1))
    return 0

def generate_router_id(device_name, role):
    """Generate router ID based on device name and role"""
    device_num = extract_device_number(device_name)
    
    if role == 'spine':
        octet = SPINE_LOOPBACK_START + device_num - 1
    elif role == 'leaf':
        octet = LEAF_LOOPBACK_START + device_num - 1
    else:
        octet = 100 + device_num
    
    return f"{LOOPBACK_BASE}{octet}"

def generate_vtep_ip(device_name):
    """Generate VTEP loopback IP for leaf switches (different from router ID)"""
    device_num = extract_device_number(device_name)
    octet = LEAF_LOOPBACK_START + device_num - 1
    return f"{VTEP_LOOPBACK_BASE}{octet}"

def generate_asn(device_name, role):
    """Generate BGP ASN based on device role"""
    if role == 'spine':
        return BASE_ASN_SPINE
    elif role == 'leaf':
        device_num = extract_device_number(device_name)
        return BASE_ASN_LEAF + device_num - 1
    else:
        return BASE_ASN_SPINE

def calculate_p2p_ips(link_index, device_type):
    """
    Calculate point-to-point IPs for spine-leaf links using /31 subnets.
    
    Address scheme: 10.0.{link_index}.{0,1}/31
    - Spine gets .0 (even)
    - Leaf gets .1 (odd)
    
    Args:
        link_index: Index of the link (0, 1, 2, ...)
        device_type: 'spine' or 'leaf'
    
    Returns:
        tuple: (local_ip, peer_ip) both as strings
    """
    if device_type == 'leaf':
        local_ip = f"{P2P_LINK_BASE}{link_index}.1/31"
        peer_ip = f"{P2P_LINK_BASE}{link_index}.0"
    else:  # spine
        local_ip = f"{P2P_LINK_BASE}{link_index}.0/31"
        peer_ip = f"{P2P_LINK_BASE}{link_index}.1"
    
    return local_ip, peer_ip

def get_device_links(device_name, clab_data):
    """
    Get detailed link information for a specific device.
    
    Returns list of dicts with:
    - remote_device: name of connected device
    - local_interface: local interface name
    - remote_interface: remote interface name
    - link_index: index of this link
    """
    links = []
    link_index = 0
    
    for link in clab_data['topology'].get('links', []):
        endpoints = link['endpoints']
        dev1_name, intf1_name = endpoints[0].split(':')
        dev2_name, intf2_name = endpoints[1].split(':')
        
        if dev1_name == device_name:
            links.append({
                'remote_device': dev2_name,
                'local_interface': intf1_name,
                'remote_interface': intf2_name,
                'link_index': link_index
            })
        elif dev2_name == device_name:
            links.append({
                'remote_device': dev1_name,
                'local_interface': intf2_name,
                'remote_interface': intf1_name,
                'link_index': link_index
            })
        
        link_index += 1
    
    return links

def get_connected_devices(device_name, clab_data):
    """Get list of devices connected to this device from topology"""
    connected = []
    links = clab_data['topology'].get('links', [])
    
    for link in links:
        endpoints = link['endpoints']
        dev1_name, _ = endpoints[0].split(':')
        dev2_name, _ = endpoints[1].split(':')
        
        if dev1_name == device_name:
            connected.append(dev2_name)
        elif dev2_name == device_name:
            connected.append(dev1_name)
    
    return connected

def calculate_topology_depth(clab_data):
    """
    Calculate the depth of the network topology to determine eBGP multihop value.
    Returns the maximum number of hops between any spine and leaf device.
    """
    nodes = clab_data['topology']['nodes']
    
    # Identify all spine and leaf devices
    spines = [name for name in nodes.keys() if determine_device_role(name) == 'spine']
    leafs = [name for name in nodes.keys() if determine_device_role(name) == 'leaf']
    
    if not spines or not leafs:
        # If no spine-leaf topology detected, return default
        return 2
    
    # Build adjacency graph
    adjacency = {}
    links = clab_data['topology'].get('links', [])
    
    for link in links:
        endpoints = link['endpoints']
        dev1_name, _ = endpoints[0].split(':')
        dev2_name, _ = endpoints[1].split(':')
        
        if dev1_name not in adjacency:
            adjacency[dev1_name] = []
        if dev2_name not in adjacency:
            adjacency[dev2_name] = []
        
        adjacency[dev1_name].append(dev2_name)
        adjacency[dev2_name].append(dev1_name)
    
    # BFS to find shortest path from a spine to a leaf
    def bfs_shortest_path(start, targets):
        """Find shortest path from start to any target using BFS"""
        if start in targets:
            return 0
        
        queue = [(start, 0)]
        visited = {start}
        
        while queue:
            current, depth = queue.pop(0)
            
            for neighbor in adjacency.get(current, []):
                if neighbor in visited:
                    continue
                    
                if neighbor in targets:
                    return depth + 1
                
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))
        
        return 0  # No path found
    
    # Find maximum depth from any spine to any leaf
    max_depth = 0
    for spine in spines:
        depth = bfs_shortest_path(spine, set(leafs))
        max_depth = max(max_depth, depth)
    
    # eBGP multihop should be at least depth + 1 for safety
    # For direct spine-leaf: depth=1, multihop=2
    # For spine-superspine-leaf: depth=2, multihop=3
    ebgp_multihop = max_depth + 1
    
    logger.info(f"Detected topology depth: {max_depth} hops, setting eBGP multihop to {ebgp_multihop}")
    
    return ebgp_multihop

def get_or_create_vlan(nb, site, vlan_id, vlan_name):
    """
    Get or create a VLAN in NetBox.
    
    Args:
        nb: NetBox API object
        site: Site object
        vlan_id: VLAN ID (integer)
        vlan_name: VLAN name (string)
    
    Returns:
        VLAN object
    """
    try:
        # Check if VLAN exists at this site with this ID
        vlan = nb.ipam.vlans.get(site_id=site.id, vid=vlan_id)
        
        if not vlan:
            logger.info(f"Creating VLAN {vlan_id} ({vlan_name}) at site {site.name}")
            vlan = nb.ipam.vlans.create(
                vid=vlan_id,
                name=vlan_name,
                site=site.id
            )
        else:
            logger.debug(f"VLAN {vlan_id} already exists at site {site.name}")
        
        return vlan
    except RequestError as e:
        logger.error(f"NetBox API error creating VLAN {vlan_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating VLAN {vlan_id}: {e}")
        return None

def create_loopback_interface(nb, device, loopback_id, ip_address):
    """
    Create a loopback interface on a device and assign an IP address.
    
    Args:
        nb: NetBox API object
        device: Device object
        loopback_id: Loopback interface number (0 for Loopback0, 1 for Loopback1)
        ip_address: IP address with prefix (e.g., "10.255.255.1/32")
    
    Returns:
        Interface object
    """
    try:
        loopback_name = f"Loopback{loopback_id}"
        
        # Get or create the loopback interface
        interface = nb.dcim.interfaces.get(device_id=device.id, name=loopback_name)
        
        if not interface:
            logger.info(f"Creating {loopback_name} interface on {device.name}")
            interface = nb.dcim.interfaces.create(
                device=device.id,
                name=loopback_name,
                type='virtual'
            )
        else:
            logger.debug(f"{loopback_name} already exists on {device.name}")
        
        # Assign IP address to the interface
        assign_interface_ip(nb, interface, ip_address, f"{loopback_name} IP")
        
        return interface
        
    except RequestError as e:
        logger.error(f"NetBox API error creating {loopback_name} on {device.name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating {loopback_name} on {device.name}: {e}")
        return None

def assign_vlans_to_device(nb, device, site):
    """
    Create VLANs in NetBox for leaf devices.
    
    Args:
        nb: NetBox API object
        device: Device object
        site: Site object
    """
    try:
        logger.info(f"Creating VLANs for {device.name}")
        
        for vlan_def in DEFAULT_VLANS:
            get_or_create_vlan(nb, site, vlan_def['vid'], vlan_def['name'])
        
        logger.info(f"Successfully processed VLANs for {device.name}")
        
    except Exception as e:
        logger.error(f"Error assigning VLANs to {device.name}: {e}")

def generate_spine_config_context(device_name, device_data, clab_data, all_devices):
    """Generate config context for spine switches (BGP config only, no duplicated data)"""
    router_id = generate_router_id(device_name, 'spine')
    asn = generate_asn(device_name, 'spine')
    
    # Calculate eBGP multihop based on topology depth
    ebgp_multihop = calculate_topology_depth(clab_data)
    
    # Get all links for this spine
    all_links = get_device_links(device_name, clab_data)
    
    # Filter for leaf connections
    leaf_links = [link for link in all_links if determine_device_role(link['remote_device']) == 'leaf']
    
    # Build underlay BGP neighbor list WITH peer IPs
    underlay_neighbors = []
    for link in leaf_links:
        leaf_name = link['remote_device']
        leaf_asn = generate_asn(leaf_name, 'leaf')
        
        # Calculate P2P IPs for this link
        local_ip, peer_ip = calculate_p2p_ips(link['link_index'], 'spine')
        
        underlay_neighbors.append({
            "ip": peer_ip,  # KEY ADDITION - the leaf's IP on this link
            "interface": link['local_interface'],
            "peer_group": "SPINE_UNDERLAY",
            "remote_as": leaf_asn,
            "description": leaf_name
        })
    
    # Build EVPN overlay neighbor list with leaf VTEP IPs (Loopback1)
    evpn_neighbors = []
    # Get unique leaf devices (avoid duplicates if multiple links to same leaf)
    unique_leafs = list(set([link['remote_device'] for link in leaf_links]))
    for leaf in unique_leafs:
        leaf_vtep_ip = generate_vtep_ip(leaf)  # Use VTEP IP (Loopback1)
        leaf_asn = generate_asn(leaf, 'leaf')
        evpn_neighbors.append({
            "ip": leaf_vtep_ip,
            "remote_as": leaf_asn,
            "peer_group": "EVPN_OVERLAY",
            "encapsulation": "vxlan"
        })
    
    config_context = {
        "bgp": {
            "asn": asn,
            "maximum_paths": 4,
            "ecmp_paths": 4,
            "peer_groups": [
                {
                    "name": "SPINE_UNDERLAY",
                    "send_community": "extended"
                },
                {
                    "name": "EVPN_OVERLAY",
                    "update_source": "Loopback0",
                    "ebgp_multihop": ebgp_multihop,
                    "send_community": "extended"
                }
            ],
            "underlay_neighbors": underlay_neighbors,
            "evpn": {
                "neighbors": evpn_neighbors
            }
        },
        "ntp_servers": ["10.0.0.100", "10.0.0.101"],
        "dns_servers": ["10.0.0.50", "10.0.0.51"],
        "syslog_servers": ["10.0.0.200"]
    }
    
    return config_context

def generate_leaf_config_context(device_name, device_data, clab_data, all_devices):
    """Generate config context for leaf switches (BGP/VXLAN config only, no duplicated data)"""
    router_id = generate_router_id(device_name, 'leaf')
    vtep_ip = generate_vtep_ip(device_name)
    asn = generate_asn(device_name, 'leaf')
    
    # Calculate eBGP multihop based on topology depth
    ebgp_multihop = calculate_topology_depth(clab_data)
    
    # Get all links for this leaf
    all_links = get_device_links(device_name, clab_data)
    
    # Filter for spine connections
    spine_links = [link for link in all_links if determine_device_role(link['remote_device']) == 'spine']
    
    # Build underlay BGP neighbor list WITH peer IPs
    underlay_neighbors = []
    for link in spine_links:
        spine_name = link['remote_device']
        spine_asn = generate_asn(spine_name, 'spine')
        
        # Calculate P2P IPs for this link
        local_ip, peer_ip = calculate_p2p_ips(link['link_index'], 'leaf')
        
        underlay_neighbors.append({
            "ip": peer_ip,  # KEY ADDITION - the spine's IP on this link
            "interface": link['local_interface'],
            "peer_group": "LEAF_UNDERLAY",
            "remote_as": spine_asn,
            "description": spine_name
        })
    
    # Build EVPN overlay neighbor list with spine router IDs
    evpn_neighbors = []
    # Get unique spine devices (avoid duplicates if multiple links to same spine)
    unique_spines = list(set([link['remote_device'] for link in spine_links]))
    for spine in unique_spines:
        spine_router_id = generate_router_id(spine, 'spine')
        spine_asn = generate_asn(spine, 'spine')
        evpn_neighbors.append({
            "ip": spine_router_id,
            "remote_as": spine_asn,
            "peer_group": "EVPN_OVERLAY",
            "encapsulation": "vxlan"
        })
    
    # Generate VLAN-to-VNI mappings (still kept in config_context for automation)
    vlan_vni_mappings = []
    for vlan in DEFAULT_VLANS:
        vlan_vni_mappings.append({
            "vlan": vlan["vid"],
            "vni": 10000 + vlan["vid"]  # VLAN 10 -> VNI 10010
        })
    
    config_context = {
        "vxlan": {
            "vtep_source_interface": "Loopback1",
            "udp_port": 4789,
            "vlan_vni_mappings": vlan_vni_mappings
        },
        "bgp": {
            "asn": asn,
            "maximum_paths": 4,
            "ecmp_paths": 4,
            "peer_groups": [
                {
                    "name": "LEAF_UNDERLAY",
                    "send_community": "extended"
                },
                {
                    "name": "EVPN_OVERLAY",
                    "update_source": "Loopback1",
                    "ebgp_multihop": ebgp_multihop,
                    "send_community": "extended"
                }
            ],
            "underlay_neighbors": underlay_neighbors,
            "evpn": {
                "neighbors": evpn_neighbors
            }
        },
        "ntp_servers": ["10.0.0.100", "10.0.0.101"],
        "dns_servers": ["10.0.0.50", "10.0.0.51"],
        "syslog_servers": ["10.0.0.200"]
    }
    
    return config_context

def apply_config_context(nb, device, config_context, device_name):
    """Apply config context to a device in NetBox"""
    try:
        # NetBox stores config context as local_context_data on the device
        logger.info(f"Applying config context to {device_name}")
        device.local_context_data = config_context
        device.save()
        logger.info(f"Successfully applied config context to {device_name}")
    except RequestError as e:
        logger.error(f"NetBox API error applying config context to {device_name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error applying config context to {device_name}: {e}")

def create_devices(nb, clab_data, site, skip_config_context=False):
    """Create devices from ContainerLab topology"""
    devices = {}
    nodes = clab_data['topology']['nodes']
    
    # Extract management subnet prefix length from clab.yml
    mgmt_config = clab_data.get('mgmt', {})
    mgmt_subnet = mgmt_config.get('ipv4-subnet')
    
    if not mgmt_subnet:
        logger.error("No mgmt.ipv4-subnet found in ContainerLab YAML file")
        raise ValueError("Management subnet not defined in clab.yml")
    
    if '/' not in mgmt_subnet:
        logger.error(f"Management subnet '{mgmt_subnet}' does not contain a prefix length")
        raise ValueError("Management subnet must include prefix length (e.g., 192.168.121.0/24)")
    
    mgmt_prefix_len = mgmt_subnet.split('/')[-1]
    logger.info(f"Using management subnet: {mgmt_subnet} (prefix length: /{mgmt_prefix_len})")
    
    if skip_config_context:
        logger.info("Config context generation is disabled (--skip-config-context)")
    
    logger.info(f"Processing {len(nodes)} devices")
    
    for node_name, node_data in nodes.items():
        try:
            kind = node_data.get('kind', 'linux')
            mgmt_ip = node_data.get('mgmt-ipv4')
            
            # Get or create manufacturer
            manufacturer_name = MANUFACTURER_MAP.get(kind, 'Generic')
            manufacturer = get_or_create_manufacturer(nb, manufacturer_name)
            
            # Get or create device type
            device_type = get_or_create_device_type(nb, kind, manufacturer.id)
            
            # Determine device role name based on kind and device name
            if kind == 'ceos':
                # Determine if spine or leaf based on hostname
                detected_role = determine_device_role(node_name)
                if detected_role == 'spine':
                    device_role_name = 'Spine'
                elif detected_role == 'leaf':
                    device_role_name = 'Leaf'
                else:
                    device_role_name = 'Network Device'  # Fallback for other network devices
            elif kind in ['linux', 'alpine']:
                # Check if it's named like a server/host
                node_lower = node_name.lower()
                if any(prefix in node_lower for prefix in ['server', 'host', 'client', 'alpine']):
                    device_role_name = 'Server'
                else:
                    device_role_name = 'Host'
            else:
                device_role_name = 'Host'
            
            # Get or create device role
            role = get_or_create_device_role(nb, device_role_name)
            
            # Check if device exists
            device = nb.dcim.devices.get(name=node_name)
            if not device:
                logger.info(f"Creating device: {node_name}")
                device = nb.dcim.devices.create(
                    name=node_name,
                    device_type=device_type.id,
                    role=role.id,
                    site=site.id
                )
            else:
                logger.info(f"Device already exists: {node_name}")
            
            devices[node_name] = device
            
            # Set ansible_network_os only for network devices (not servers/hosts)
            if kind == 'ceos':
                ansible_os = get_ansible_network_os(kind, manufacturer_name)
                set_device_custom_fields(nb, device, ansible_os)
            
            # Determine device type (spine/leaf)
            device_role = determine_device_role(node_name)
            
            # Create loopback interfaces and VLANs for network devices
            if device_role in ['spine', 'leaf']:
                # Create Loopback0 with router ID
                router_id = generate_router_id(node_name, device_role)
                create_loopback_interface(nb, device, 0, f"{router_id}/32")
                
                # Create Loopback1 with VTEP IP for leaf switches
                if device_role == 'leaf':
                    vtep_ip = generate_vtep_ip(node_name)
                    create_loopback_interface(nb, device, 1, f"{vtep_ip}/32")
                    
                    # Create VLANs for leaf switches
                    assign_vlans_to_device(nb, device, site)
            
            # Apply config context for network devices (unless skipped)
            if not skip_config_context:
                if device_role in ['spine', 'leaf']:
                    if device_role == 'spine':
                        config_context = generate_spine_config_context(node_name, node_data, clab_data, nodes)
                    elif device_role == 'leaf':
                        config_context = generate_leaf_config_context(node_name, node_data, clab_data, nodes)
                    
                    apply_config_context(nb, device, config_context, node_name)
            
            # Create management IP if specified
            if mgmt_ip:
                create_management_ip(nb, device, mgmt_ip, mgmt_prefix_len)
            
            # Parse exec commands for IP assignments (linux/alpine containers)
            exec_commands = node_data.get('exec', [])
            if exec_commands and kind in ['linux', 'alpine']:
                parse_exec_ip_assignments(nb, device, exec_commands)
                
        except Exception as e:
            logger.error(f"Error processing device {node_name}: {e}")
            continue
    
    logger.info(f"Successfully processed {len(devices)} devices")
    return devices

def parse_exec_ip_assignments(nb, device, exec_commands):
    """
    Parse exec commands from containerlab to find IP address assignments.
    Extracts IPs from commands like: ip addr add 192.168.10.1/24 dev eth1
    """
    if not exec_commands:
        return
    
    try:
        for cmd in exec_commands:
            # Match: ip addr add <IP>/<prefix> dev <interface>
            match = re.search(r'ip\s+addr\s+add\s+(\d+\.\d+\.\d+\.\d+/\d+)\s+dev\s+(\S+)', cmd)
            if match:
                ip_with_prefix = match.group(1)
                interface_name = match.group(2)
                
                logger.info(f"Found IP assignment in exec: {ip_with_prefix} on {interface_name} for {device.name}")
                
                # Get or create the interface
                interface = get_or_create_interface(nb, device, interface_name)
                if interface:
                    # Assign the IP to the interface
                    assign_interface_ip(nb, interface, ip_with_prefix, f"Container data IP from exec")
                else:
                    logger.warning(f"Could not create interface {interface_name} on {device.name}")
    except Exception as e:
        logger.error(f"Error parsing exec commands for {device.name}: {e}")

def create_management_ip(nb, device, mgmt_ip, prefix_len):
    """Create management IP address for a device"""
    try:
        # Add prefix length from the management subnet if not already included
        if '/' not in mgmt_ip:
            ip_addr = f"{mgmt_ip}/{prefix_len}"
        else:
            ip_addr = mgmt_ip
        
        # Validate the IP address format
        try:
            from ipaddress import ip_interface as validate_ip
            validate_ip(ip_addr)
        except ValueError as e:
            logger.error(f"Invalid IP address format {ip_addr}: {e}")
            return
        
        existing_ip = nb.ipam.ip_addresses.get(address=ip_addr)
        
        if not existing_ip:
            logger.info(f"Creating management IP: {ip_addr} for {device.name}")
            # NetBox requires assignment to an interface, not directly to device
            # Create or get a management interface first
            mgmt_interface = get_or_create_interface(nb, device, 'mgmt0')
            
            if not mgmt_interface:
                logger.error(f"Could not create management interface for {device.name}")
                return
            
            ip_obj = nb.ipam.ip_addresses.create(
                address=ip_addr,
                assigned_object_type='dcim.interface',
                assigned_object_id=mgmt_interface.id,
                description=f"Management IP for {device.name}"
            )
            
            # Set as primary IP for the device
            device.primary_ip4 = ip_obj.id
            device.save()
        else:
            logger.debug(f"IP already exists: {ip_addr}")
    except RequestError as e:
        logger.error(f"NetBox API error creating IP {ip_addr} for {device.name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error creating IP for {device.name}: {e}")

def assign_interface_ip(nb, interface, ip_with_mask, description=""):
    """Assign an IP address to an interface in NetBox"""
    try:
        # Check if IP already exists
        existing_ip = nb.ipam.ip_addresses.get(address=ip_with_mask)
        
        if not existing_ip:
            logger.info(f"Assigning IP {ip_with_mask} to {interface.device.name}:{interface.name}")
            
            # Create the IP address
            ip_obj = nb.ipam.ip_addresses.create(
                address=ip_with_mask,
                assigned_object_type='dcim.interface',
                assigned_object_id=interface.id,
                description=description
            )
        else:
            # Update existing IP if not assigned to this interface
            if not existing_ip.assigned_object_id or existing_ip.assigned_object_id != interface.id:
                logger.info(f"Updating IP {ip_with_mask} assignment to {interface.device.name}:{interface.name}")
                existing_ip.assigned_object_type = 'dcim.interface'
                existing_ip.assigned_object_id = interface.id
                if description:
                    existing_ip.description = description
                existing_ip.save()
            else:
                logger.debug(f"IP {ip_with_mask} already assigned to {interface.device.name}:{interface.name}")
                
    except RequestError as e:
        logger.error(f"NetBox API error assigning IP {ip_with_mask} to {interface.device.name}:{interface.name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error assigning IP to interface: {e}")

def create_interfaces_and_links(nb, clab_data, devices):
    """Create interfaces and links from ContainerLab topology"""
    links = clab_data['topology'].get('links', [])
    
    logger.info(f"Processing {len(links)} links")
    successful_links = 0
    
    for link_index, link in enumerate(links):
        try:
            endpoints = link['endpoints']
            
            # Parse endpoints (format: "device:interface")
            device1_name, intf1_name = endpoints[0].split(':')
            device2_name, intf2_name = endpoints[1].split(':')
            
            # Get devices
            device1 = devices.get(device1_name)
            device2 = devices.get(device2_name)
            
            if not device1 or not device2:
                logger.warning(f"Could not find devices for link {endpoints}")
                continue
            
            # Determine device roles
            device1_role = determine_device_role(device1_name)
            device2_role = determine_device_role(device2_name)
            
            # Create interfaces
            intf1 = get_or_create_interface(nb, device1, intf1_name)
            intf2 = get_or_create_interface(nb, device2, intf2_name)
            
            # Assign IP addresses for spine-leaf links
            if intf1 and intf2 and {device1_role, device2_role} == {'spine', 'leaf'}:
                # Set descriptions (routed interfaces don't need mode set)
                intf1.description = f"to_{device2_name}"
                intf2.description = f"to_{device1_name}"
                
                intf1.save()
                intf2.save()
                
                # Calculate and assign IPs
                if device1_role == 'spine':
                    spine_intf, leaf_intf = intf1, intf2
                    spine_role, leaf_role = device1_role, device2_role
                else:
                    spine_intf, leaf_intf = intf2, intf1
                    spine_role, leaf_role = device2_role, device1_role
                
                spine_ip, _ = calculate_p2p_ips(link_index, 'spine')
                leaf_ip, _ = calculate_p2p_ips(link_index, 'leaf')
                
                assign_interface_ip(nb, spine_intf, spine_ip, f"P2P link {link_index}")
                assign_interface_ip(nb, leaf_intf, leaf_ip, f"P2P link {link_index}")
            
            # Set descriptions for leaf-to-host connections (no IP assignment)
            elif intf1 and intf2 and 'leaf' in {device1_role, device2_role} and 'unknown' in {device1_role, device2_role}:
                # Parse link labels for VLAN configuration
                link_labels = link.get('labels', {})
                mode = link_labels.get('mode', None)
                vlan_id = link_labels.get('vlan', None)
                
                # Determine which interface is on the leaf switch
                if device1_role == 'leaf':
                    leaf_intf = intf1
                    server_intf = intf2
                    leaf_device = device1
                else:
                    leaf_intf = intf2
                    server_intf = intf1
                    leaf_device = device2
                
                # Set descriptions
                intf1.description = f"to_{device2_name}"
                intf2.description = f"to_{device1_name}"
                
                # Configure access mode if specified in link labels
                if mode == 'access' and vlan_id:
                    logger.info(f"Configuring {leaf_device.name}:{leaf_intf.name} as access port on VLAN {vlan_id}")
                    
                    # Get site for VLAN lookup
                    site = nb.dcim.sites.get(id=leaf_device.site.id)
                    
                    # Get or create the VLAN
                    vlan = nb.ipam.vlans.get(site_id=site.id, vid=vlan_id)
                    if not vlan:
                        logger.warning(f"VLAN {vlan_id} not found at site {site.name}, creating it")
                        vlan = get_or_create_vlan(nb, site, vlan_id, f"VLAN{vlan_id}")
                    
                    if vlan:
                        # Set interface mode to access
                        leaf_intf.mode = 'access'
                        leaf_intf.untagged_vlan = vlan.id
                        logger.info(f"Set {leaf_device.name}:{leaf_intf.name} to access mode with untagged VLAN {vlan_id}")
                
                intf1.save()
                intf2.save()
            
            # Create cable connection
            if intf1 and intf2:
                create_cable(nb, intf1, intf2)
                successful_links += 1
                
        except ValueError as e:
            logger.error(f"Error parsing link endpoints {link}: {e}")
            continue
        except Exception as e:
            logger.error(f"Error processing link {link}: {e}")
            continue
    
    logger.info(f"Successfully processed {successful_links}/{len(links)} links")

def get_or_create_interface(nb, device, intf_name):
    """Get or create an interface on a device"""
    try:
        interface = nb.dcim.interfaces.get(device_id=device.id, name=intf_name)
        
        if not interface:
            logger.info(f"Creating interface: {device.name}:{intf_name}")
            # Use 1000base-t for eth interfaces, other for management
            if intf_name.startswith('eth'):
                intf_type = '1000base-t'
            elif intf_name.startswith('et'):
                intf_type = '10gbase-x-sfpp'
            else:
                # Management interface
                intf_type = '1000base-t'
            
            interface = nb.dcim.interfaces.create(
                device=device.id,
                name=intf_name,
                type=intf_type
            )
        else:
            logger.debug(f"Interface already exists: {device.name}:{intf_name}")
        
        return interface
    except RequestError as e:
        logger.error(f"NetBox API error creating interface {device.name}:{intf_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating interface {device.name}:{intf_name}: {e}")
        return None

def create_cable(nb, intf1, intf2):
    """Create a cable connection between two interfaces"""
    try:
        # Check if cable already exists
        if intf1.cable or intf2.cable:
            logger.debug(f"Cable already exists between {intf1.device.name}:{intf1.name} and {intf2.device.name}:{intf2.name}")
            return
        
        logger.info(f"Creating cable: {intf1.device.name}:{intf1.name} <-> {intf2.device.name}:{intf2.name}")
        
        cable = nb.dcim.cables.create(
            a_terminations=[{
                'object_type': 'dcim.interface',
                'object_id': intf1.id
            }],
            b_terminations=[{
                'object_type': 'dcim.interface',
                'object_id': intf2.id
            }]
        )
    except RequestError as e:
        logger.error(f"NetBox API error creating cable between {intf1.device.name}:{intf1.name} and {intf2.device.name}:{intf2.name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error creating cable: {e}")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Synchronize ContainerLab topology to NetBox',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables Required:
  NETBOX_URL        NetBox instance URL (e.g., https://netbox.example.com)
  NETBOX_APITOKEN   NetBox API token

Examples:
  %(prog)s clab.yml
  %(prog)s --no-ssl-verify clab.yml
  %(prog)s --skip-config-context clab.yml
        """
    )
    parser.add_argument('clab_file', help='Path to ContainerLab YAML file')
    parser.add_argument('--no-ssl-verify', action='store_true',
                        help='Disable SSL certificate verification (insecure)')
    parser.add_argument('--skip-config-context', action='store_true',
                        help='Skip generating and applying config contexts to devices')
    
    args = parser.parse_args()
    
    # Get NetBox configuration from environment variables
    NETBOX_URL = os.environ.get('NETBOX_URL')
    NETBOX_APITOKEN = os.environ.get('NETBOX_APITOKEN')
    
    if not NETBOX_URL:
        logger.error("NETBOX_URL environment variable is not set")
        sys.exit(1)
    
    if not NETBOX_APITOKEN:
        logger.error("NETBOX_APITOKEN environment variable is not set")
        sys.exit(1)
    
    # Disable SSL warnings if requested
    if args.no_ssl_verify:
        logger.warning("SSL certificate verification is disabled - this is insecure!")
        urllib3.disable_warnings(InsecureRequestWarning)
    
    try:
        # Load ContainerLab YAML
        logger.info(f"Loading ContainerLab file: {args.clab_file}")
        clab_data = load_clab_yaml(args.clab_file)
        
        # Connect to NetBox
        logger.info(f"Connecting to NetBox: {NETBOX_URL}")
        try:
            nb = pynetbox.api(NETBOX_URL, token=NETBOX_APITOKEN)
            
            # Disable SSL verification if requested
            if args.no_ssl_verify:
                nb.http_session.verify = False
            
            # Test connection
            nb.dcim.sites.count()
            logger.info("Successfully connected to NetBox")
        except Exception as e:
            logger.error(f"Failed to connect to NetBox: {e}")
            sys.exit(1)
        
        # Create site from clab name
        clab_name = clab_data.get('name', 'containerlab')
        site = get_or_create_site(nb, clab_name)
        logger.info(f"Using site: {site.name}")
        
        # Ensure ansible_network_os custom field exists
        logger.info("Checking/creating custom field for ansible_network_os...")
        ensure_custom_field_exists(nb)
        
        # Create devices
        logger.info("=" * 50)
        logger.info("Creating devices...")
        logger.info("=" * 50)
        devices = create_devices(nb, clab_data, site, skip_config_context=args.skip_config_context)
        
        # Create interfaces and links
        logger.info("=" * 50)
        logger.info("Creating interfaces and links...")
        logger.info("=" * 50)
        create_interfaces_and_links(nb, clab_data, devices)
        
        logger.info("=" * 50)
        logger.info("✓ Synchronization complete!")
        logger.info("=" * 50)
        
    except KeyboardInterrupt:
        logger.warning("Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error during synchronization: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()