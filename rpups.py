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

def get_21700_percent(voltage_mv):
    """Calculate battery percentage based on standard 21700 discharge curve."""
    curve = [
        (4200, 100), (4100, 93), (4000, 83), (3900, 73),
        (3800, 60), (3700, 45), (3600, 30), (3500, 15),
        (3400, 8), (3300, 3), (3200, 1), (3000, 0)
    ]
    if voltage_mv >= 4200: return 100
    if voltage_mv <= 3000: return 0
    for i in range(len(curve) - 1):
        v_high, p_high = curve[i]
        v_low, p_low = curve[i+1]
        if v_low <= voltage_mv <= v_high:
            return int(p_low + (voltage_mv - v_low) * (p_high - p_low) / (v_high - v_low))
    return 0

def get_ups_data():
    try:
        bus = smbus.SMBus(BUS_ID)
        
        # Battery Data
        batt_data = bus.read_i2c_block_data(ADDR, 0x20, 0x0C)
        voltage = batt_data[0] | batt_data[1] << 8
        current = (batt_data[2] | batt_data[3] << 8)
        if(current > 0x7FFF):
            current -= 0xFFFF
        hw_percent = int(batt_data[4] | batt_data[5] << 8) # Hardware percent (often inaccurate)
        hw_capacity = batt_data[6] | batt_data[7] << 8
        
        # State
        if current < 0:
            state = "Battery"
        else:
            state = "AC"
            
        # Cell Voltages
        cell_data = bus.read_i2c_block_data(ADDR, 0x30, 0x08)
        v1 = cell_data[0] | cell_data[1] << 8
        v2 = cell_data[2] | cell_data[3] << 8
        v3 = cell_data[4] | cell_data[5] << 8
        v4 = cell_data[6] | cell_data[7] << 8
        
        # Calculate raw usable percentage based on the lowest cell
        lowest_cell_v = min(v1, v2, v3, v4)
        percent_raw = get_21700_percent(lowest_cell_v)
        
        # Auto-Calibration
        config = load_config()
        # Only calibrate when battery is fully charged and resting (or trickle charging)
        if current >= 0 and hw_percent >= 95 and percent_raw > 0:
            needs_save = False
            if config.get('max_raw_percent', 0) < percent_raw:
                config['max_raw_percent'] = percent_raw
                needs_save = True
            if config.get('max_hw_capacity', 0) < hw_capacity:
                config['max_hw_capacity'] = hw_capacity
                needs_save = True
            if needs_save:
                try:
                    save_config(config)
                except PermissionError:
                    pass # Ignore if called by non-root CLI user
                    
        # Scale to 0-100% relative to the degraded maximum capacity
        max_raw = config.get('max_raw_percent', 41) # Default to 41 based on user's current degraded state
        if max_raw <= 0: max_raw = 100
        
        percent = int((percent_raw / max_raw) * 100)
        if percent > 100: percent = 100
        if percent < 0: percent = 0
        
        # Scale capacity proportionally
        max_cap = config.get('max_hw_capacity', 4632)
        capacity = int((percent / 100.0) * max_cap)
        
        return {
            "state": state,
            "voltage": voltage,
            "current": current,
            "percent": percent,
            "capacity": capacity,
            "v1": v1,
            "v2": v2,
            "v3": v3,
            "v4": v4
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

def cmd_log(args):
    log_file = "/etc/rpups/rpups.log"
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                print(f.read(), end="")
        except Exception as e:
            print(f"Error reading log file: {e}", file=sys.stderr)
    else:
        print("No logs available yet.")

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
            
            # Check if any cell voltage drops below critical safe limit (3150 mV)
            LOW_VOL = 3150
            is_low_voltage = any(data[f'v{i}'] < LOW_VOL for i in range(1, 5))
            
            # current < 0 means discharging (running on battery)
            if (percent <= threshold or is_low_voltage) and current < 0:
                reason = "Cell voltage too low" if is_low_voltage else f"Battery at {percent}%"
                msg = f"RPups daemon powering OFF ({reason}). State: {data['state']}, Capacity: {data['capacity']} mAh, Percentage: {data['percent']}%, Poweroff threshold: {threshold}%. Shutting down..."
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
    
    # log command
    parser_log = subparsers.add_parser("log", help="Show recent startup and shutdown logs")
    
    # daemon command (internal)
    parser_daemon = subparsers.add_parser("daemon", help=argparse.SUPPRESS)
    
    args = parser.parse_args()
    
    if args.command == "remain":
        cmd_remain(args)
    elif args.command == "state":
        cmd_state(args)
    elif args.command == "poweroff":
        cmd_poweroff(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "daemon":
        daemon_mode()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
