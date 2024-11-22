import re
import csv
import os
from collections import defaultdict


def parse_ios_xe_config(config_file):
    """
    Parses the IOS-XE configuration file to extract:
    - Hostname
    - Serial Number
    - SNMP Location
    - Interface details (GigabitEthernet, Loopback, subinterfaces)
    """
    # Check if the file exists
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"The configuration file {config_file} does not exist.")

    # Read the configuration file
    with open(config_file, 'r') as file:
        config = file.read()

    # Initialize the result dictionary
    result = {
        "hostname": None,
        "serial_number": None,
        "location": None,
        "system_ip": None,
        "interfaces": [],
        "counters": defaultdict(int)  # Keeps track of unique variable names
    }

    # Extract hostname
    hostname_match = re.search(r"^hostname\s+(\S+)", config, re.MULTILINE)
    result["hostname"] = hostname_match.group(1) if hostname_match else "unknown"

    # Extract serial number in format ISR1000/K9-XXXXXXXXXXX
    serial_match = re.search(r"^license\s+udi\s+pid\s+(\S+)\s+sn\s+(\S+)", config, re.MULTILINE)
    result["serial_number"] = f"{serial_match.group(1)}-{serial_match.group(2)}" if serial_match else "not available"

    # Extract SNMP location
    location_match = re.search(r"^snmp-server location\s+(.+)", config, re.MULTILINE)
    result["location"] = location_match.group(1) if location_match else "unknown"

    # Extract interface details
    interface_pattern = re.compile(
        r"^interface\s+(GigabitEthernet[\d/.]+|Loopback\d+)(.*?)^(?=\S)", 
        re.MULTILINE | re.DOTALL
    )
    interfaces = interface_pattern.findall(config)

    for interface, body in interfaces:
        # Initialize interface data
        interface_data = {
            "name": interface,
            "description": None,
            "ip_address": None,
            "dot1q_vlan": None
        }

        # Extract description
        description_match = re.search(r"^\s+description\s+(.+)", body, re.MULTILINE)
        if description_match:
            interface_data["description"] = description_match.group(1)

         # Special handling for Loopback0
        if interface == "Loopback0":
            # Extract IP address without mask for system_ip
            ip_address_match = re.search(r"^\s+ip address\s+(\S+)\s+\S+", body, re.MULTILINE)
            if ip_address_match:
                result["system_ip"] = ip_address_match.group(1)  # Save the IP address without mask
                print(f"DEBUG: Extracted system_ip: {result['system_ip']}")

            # Extract full IP address with mask (if needed elsewhere)
            ip_address_mask_match = re.search(r"^\s+ip address\s+(\S+)\s+(\S+)", body, re.MULTILINE)
            if ip_address_mask_match:
                interface_data["ip_address"] = f"{ip_address_mask_match.group(1)} {ip_address_mask_match.group(2)}"


        #Extract IP address with mask
        ip_address_mask_match = re.search(r"^\s+ip address\s+(\S+)\s+(\S+)", body, re.MULTILINE)
        if ip_address_mask_match:
            interface_data["ip_address"] = f"{ip_address_mask_match.group(1)} {ip_address_mask_match.group(2)}"

        # Extract VLAN ID for subinterfaces
        dot1q_match = re.search(r"^\s+encapsulation\s+dot1Q\s+(\d+)", body, re.MULTILINE)
        if dot1q_match:
            interface_data["dot1q_vlan"] = dot1q_match.group(1)

        # Increment counters and create unique variable names
        for key in ["ip_address", "description", "dot1q_vlan"]:
            if interface_data[key]:
                result["counters"][key] += 1
                unique_key = f"{key}_{result['counters'][key]}"
                interface_data[unique_key] = interface_data.pop(key)

        # Append interface data to the result
        result["interfaces"].append(interface_data)

    return result


def parse_input_csv(csv_file):
    """
    Reads the input CSV file, extracts variables and values, and normalizes their keys for comparison.
    """
    # Check if the file exists
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"The CSV file {csv_file} does not exist.")

    # Define the normalization map
    normalization_map = {
        "csv-deviceId": "serial_number",
        "location": "location",
        "host-name": "hostname",
        "system-ip": "system_ip",
        "Loopback0": "ip_address_1",
        "LAN10-IP-Address": "ip_address_2",
        "LAN10-Description": "description_1",
        "LAN10-VLAN-ID": "dot1q_vlan_1",
         "WAN1-IP-Addr": "ip_address_3",
        "WAN1-Descr": "description_3",
        "WAN2-IP-Addr": "ip_address_4",
        "WAN2-descr": "description_4"
    }

    # Read the CSV file
    with open(csv_file, 'r', encoding='utf-8') as file:
        reader = csv.reader(file)
        rows = list(reader)

    # Check for at least two rows
    if len(rows) < 2:
        raise ValueError("The CSV file must have at least two rows (variables and values).")

    # Extract variables and their corresponding values
    variables = rows[0]  # First row contains variables
    values = rows[1]     # Second row contains values
    # Normalize variables and map values
    normalized_data = {}
    for variable, value in zip(variables, values):
        normalized_key = normalization_map.get(variable.strip())
        if normalized_key:
            normalized_data[normalized_key] = value.strip()
            print(f"DEBUG: Mapped {variable} to {normalized_key} with value {value.strip()}")
        else:
            print(f"DEBUG: Skipped unmapped variable {variable}")
    print(f"DEBUG: Final normalized data: {normalized_data}")

    return normalized_data


def validate_data(config_data, csv_data, validation_file_path):
    """
    Compares configuration data with filtered CSV data and saves all comparisons to a validation file.
    """
    validation_results = []

    # Compare hostname, location, serial number, and system-ip
    for key in ["hostname", "location", "serial_number", "system_ip"]:
        config_value = config_data.get(key, "N/A")
        csv_value = csv_data.get(key, "N/A")
        print(f"DEBUG: Key={key}, Config Value={config_value}, CSV Value={csv_value}")
        match_status = "Matched" if config_value == csv_value else "Mismatched"
        validation_results.append({
            "Field": key,
            "Config Value": config_value,
            "CSV Value": csv_value,
            "Interface": None,
            "Match Status": match_status
        })

    # Compare interfaces
    for interface in config_data["interfaces"]:
        for key, value in interface.items():
            if key == "ip_address_6":
                continue  # Skip ip_address_6
            if key.startswith(("ip_address_", "description_", "dot1q_vlan_")):
                csv_value = csv_data.get(key, "N/A")
                match_status = "Matched" if value == csv_value else "Mismatched"
                validation_results.append({
                    "Field": key,
                    "Config Value": value,
                    "CSV Value": csv_value,
                    "Interface": interface["name"],
                    "Match Status": match_status
                })

    # Save validation results to CSV
    try:
        with open(validation_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=["Field", "Config Value", "CSV Value", "Interface", "Match Status"])
            writer.writeheader()
            writer.writerows(validation_results)
    except Exception as e:
        raise IOError(f"Failed to write to validation file {validation_file_path}: {e}")


if __name__ == "__main__":
    try:
        # Input files
        config_file = r'config-file.cfg'  # Replace with your configuration file path
        csv_file = r'template-file.csv'       # Replace with your CSV file path

        # Parse the configuration file
        config_data = parse_ios_xe_config(config_file)

        # Parse and filter the CSV file
        csv_data = parse_input_csv(csv_file)

        # Get the directory of the input files
        input_directory = os.path.dirname(config_file)
        hostname = config_data["hostname"] or "unknown"

        # Create output file name for validation
        validation_csv_file = os.path.join(input_directory, f"validation_report_{hostname}.csv")

        # Validate data and save differences
        validate_data(config_data, csv_data, validation_csv_file)

        # Success message
        print(f"Validation completed. Report saved to:")
        print(f"- Validation Report: {validation_csv_file}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
    except IOError as e:
        print(f"File Error: {e}")
    except ValueError as e:
        print(f"Data Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
