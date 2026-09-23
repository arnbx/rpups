#!/usr/bin/env python3
import smbus
import time
import os
import argparse
import sys
import json
import datetime

CONFIG_FILE = "/etc/rpups/config.json"
DEFAULT_THRESHOLD = 20
ADDR = 0x2d
BUS_ID = 1

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"poweroff_threshold": DEFAULT_THRESHOLD}

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def log_persistent(message):
    log_file = "/etc/rpups/rpups.log"
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        lines = []
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                lines = f.readlines()
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{timestamp}] {message}\n")
        
        if len(lines) > 10:
            lines = lines[-10:]
            
        with open(log_file, 'w') as f:
            f.writelines(lines)
    except Exception as e:
        print(f"Failed to write persistent log: {e}", file=sys.stderr, flush=True)

def get_ups_data():
    try:
        bus = smbus.SMBus(BUS_ID)
        
        # Battery Data
        batt_data = bus.read_i2c_block_data(ADDR, 0x20, 0x0C)
        voltage = batt_data[0] | batt_data[1] << 8
        current = (batt_data[2] | batt_data[3] << 8)
        if(current > 0x7FFF):
            current -= 0xFFFF
        percent = int(batt_data[4] | batt_data[5] << 8)
        capacity = batt_data[6] | batt_data[7] << 8
        
        # State
        if current < 0:
            state = "Battery"
        else:
            state = "AC"
        
        return {
            "state": state,
            "voltage": voltage,
            "current": current,
            "percent": percent,
            "capacity": capacity
        }
    except PermissionError:
        print("Error: Permission denied. Cannot access I2C bus. Try running with sudo, or add user to i2c group.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading UPS data: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_remain(args):
    data = get_ups_data()
    if args.p:
        print(f"{data['percent']}%")
    else:
        print(f"{data['capacity']} mAh")

def cmd_state(args):
    data = get_ups_data()
    print(data['state'])

def cmd_poweroff(args):
    threshold = args.threshold
    if threshold < 0 or threshold > 100:
        print("Error: Threshold must be between 0 and 100", file=sys.stderr)
        sys.exit(1)
        
    config = load_config()
    config['poweroff_threshold'] = threshold
    
    try:
        save_config(config)
        print(f"Poweroff threshold set to {threshold}%.")
    except PermissionError:
        print("Error: Permission denied. Please run this command with sudo.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error saving config: {e}", file=sys.stderr)
        sys.exit(1)

def daemon_mode():
    # Wait a bit on startup to ensure system and i2c bus are fully initialized
    time.sleep(10)
    
    # Log startup status
    try:
        config = load_config()
        threshold = config.get("poweroff_threshold", DEFAULT_THRESHOLD)
        data = get_ups_data()
        msg = f"RPups daemon powered ON. State: {data['state']}, Capacity: {data['capacity']} mAh, Percentage: {data['percent']}%, Poweroff threshold: {threshold}%"
        print(msg, flush=True)
        log_persistent(msg)
        
        # Ensure auto-start on power is enabled (Register 0x40, Bit 0 should be 1)
        bus = smbus.SMBus(BUS_ID)
        reg_40 = bus.read_byte_data(ADDR, 0x40)
        if (reg_40 & 0x01) == 0:
            bus.write_byte_data(ADDR, 0x40, reg_40 | 0x01)
            print("Auto-start was disabled. Re-enabled it via register 0x40.", flush=True)
    except Exception as e:
        print(f"Daemon startup error: {e}", file=sys.stderr, flush=True)
        
    while True:
        try:
            config = load_config()
            threshold = config.get("poweroff_threshold", DEFAULT_THRESHOLD)
            
            data = get_ups_data()
            current = data['current']
            percent = data['percent']
            
            # current < 0 means discharging (running on battery)
            if percent <= threshold and current < 0:
                msg = f"RPups daemon powering OFF. State: {data['state']}, Capacity: {data['capacity']} mAh, Percentage: {data['percent']}%, Poweroff threshold: {threshold}%. Shutting down..."
                print(msg, flush=True)
                log_persistent(msg)
                
                # Write 0x55 to 0x01 register of 0x2d (Gives 30s to power off, UPS will wake Pi when AC is restored)
                bus = smbus.SMBus(BUS_ID)
                bus.write_byte_data(ADDR, 0x01, 0x55)
                
                time.sleep(2)
                os.system("poweroff")
                break # Exit daemon since we are shutting down
                
        except Exception as e:
            print(f"Daemon error: {e}", file=sys.stderr, flush=True)
            
        # Check every 60 seconds
        time.sleep(60)

def main():
    parser = argparse.ArgumentParser(
        description="Raspberry Pi UPS Manager (rpups)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # remain command
    parser_remain = subparsers.add_parser("remain", help="Show remaining capacity or percentage")
    parser_remain.add_argument("-p", action="store_true", help="Show battery percentage instead of capacity")
    
    # state command
    parser_state = subparsers.add_parser("state", help="Show current charging state")
    
    # poweroff command
    parser_poweroff = subparsers.add_parser("poweroff", help="Set battery percentage threshold for automatic poweroff")
    parser_poweroff.add_argument("threshold", type=int, help="Battery percentage (0-100)")
    
    # daemon command (internal)
    parser_daemon = subparsers.add_parser("daemon", help=argparse.SUPPRESS)
    
    args = parser.parse_args()
    
    if args.command == "remain":
        cmd_remain(args)
    elif args.command == "state":
        cmd_state(args)
    elif args.command == "poweroff":
        cmd_poweroff(args)
    elif args.command == "daemon":
        daemon_mode()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
