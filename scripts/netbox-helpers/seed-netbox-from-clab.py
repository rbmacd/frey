#!/usr/bin/env python3
"""
ContainerLab to NetBox Synchronization Script
Reads a clab.yml file and populates NetBox with devices, interfaces, and IPs
"""

import yaml
import pynetbox
import sys
import os
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
    'linux': 'Linux Host'
}

MANUFACTURER_MAP = {
    'ceos': 'Arista',
    'linux': 'Generic'
}

# Ansible network_os mapping for different device kinds/manufacturers
ANSIBLE_NETWORK_OS_MAP = {
    'ceos': 'eos',
    'linux': 'linux',
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
    'Generic': 'linux'
}

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

def create_devices(nb, clab_data, site_id):
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
            
            # Determine device role name
            if kind == 'ceos':
                device_role_name = 'Network Device'
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
                    site=site_id
                )
            else:
                logger.info(f"Device already exists: {node_name}")
            
            devices[node_name] = device
            
            # Determine and set ansible_network_os
            ansible_os = get_ansible_network_os(kind, manufacturer_name)
            set_device_custom_fields(nb, device, ansible_os)
            
            # Create management IP if specified
            if mgmt_ip:
                create_management_ip(nb, device, mgmt_ip, mgmt_prefix_len)
                
        except Exception as e:
            logger.error(f"Error processing device {node_name}: {e}")
            continue
    
    logger.info(f"Successfully processed {len(devices)} devices")
    return devices

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

def create_interfaces_and_links(nb, clab_data, devices):
    """Create interfaces and links from ContainerLab topology"""
    links = clab_data['topology'].get('links', [])
    
    logger.info(f"Processing {len(links)} links")
    successful_links = 0
    
    for link in links:
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
            
            # Create interfaces
            intf1 = get_or_create_interface(nb, device1, intf1_name)
            intf2 = get_or_create_interface(nb, device2, intf2_name)
            
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
        """
    )
    parser.add_argument('clab_file', help='Path to ContainerLab YAML file')
    parser.add_argument('--no-ssl-verify', action='store_true',
                        help='Disable SSL certificate verification (insecure)')
    
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
        devices = create_devices(nb, clab_data, site.id)
        
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