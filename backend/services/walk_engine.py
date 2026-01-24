import subprocess
import re
import time
import sys
from core.config import settings

class WalkEngine:
    @staticmethod
    def run_snmpwalk(host, port, community, oid, use_mibs=True):
        # 1. Sanitize Inputs (Strip whitespace)
        host = host.strip()
        oid = oid.strip()
        target = f"{host}:{port}"
        
        # 2. Build Command
        # Base command
        cmd = ["snmpwalk", "-v2c", "-c", community]

        # 3. Handle MIBs vs Raw
        if use_mibs:
            # Use MIBs: Output Enum/Names (-Oe), Load Custom MIBs (-M), Load ALL (-m)
            cmd.extend(["-Oe", "-M", f"+{settings.MIB_DIR}", "-m", "ALL"])
        else:
            # No MIBs: Numeric Output (-On) ONLY. 
            # Do NOT pass -M or -m to avoid loading errors or overhead.
            cmd.append("-On")

        # 4. Common Options (Log errors to stderr, Don't check time)
        cmd.extend(["-Le", "-u", target, oid])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                # ... (Keep existing error filtering logic) ...
                error_lines = result.stderr.splitlines()
                clean_errors = [
                    line for line in error_lines 
                    if not any(x in line for x in ["Cannot find module", "Did not find", "Bad operator", "Unlinked OID", "Undefined identifier", "MIB search path"])
                ]
                final_error = "\n".join(clean_errors) if clean_errors else result.stderr.splitlines()[-1]
                return {"error": f"snmpwalk failed: {final_error}"}

            return result.stdout.splitlines()
            
        except FileNotFoundError:
            return {"error": "snmpwalk command not found. Is Net-SNMP installed?"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def parse_output(lines, target_host, root_oid):
        # ... (Keep the rest of your parsing logic exactly the same) ...
        parsed_data = {}
        category = root_oid.split("::")[1] if "::" in root_oid else root_oid
        
        regex_mib = re.compile(r'^(.*?)::(.*?)\.(.*?) (.*)$')
        regex_raw = re.compile(r'^(.*?)\.(.*?) (.*)$')

        for line in lines:
            module = "Unknown"
            obj_name = ""
            index = ""
            raw_value = ""

            match = regex_mib.match(line)
            if match:
                module, obj_name, index, raw_value = match.groups()
            else:
                match_raw = regex_raw.match(line)
                if match_raw:
                    full_name = match_raw.group(1)
                    obj_name = full_name
                    index = match_raw.group(2)
                    raw_value = match_raw.group(3)
                else:
                    continue

            index = index.strip()
            raw_value = raw_value.strip()
            if raw_value.startswith("= "): raw_value = raw_value[2:]

            # Type Cleaning
            if ": " in raw_value:
                val_type, val_data = raw_value.split(": ", 1)
                if ": " in val_data:
                    possible_type, possible_val = val_data.split(": ", 1)
                    if possible_type.strip() in ["INTEGER", "STRING", "Gauge32", "Counter32", "Counter64", "OID", "IpAddress", "TimeTicks", "Unsigned32"]:
                        val_data = possible_val
            else:
                val_type = "Unknown"
                val_data = raw_value

            val_data = val_data.strip('"')

            if index not in parsed_data:
                parsed_data[index] = {"index": index, "labels": {}, "metrics": {}}

            is_metric = False
            metric_types = ["Counter32", "Counter64", "Gauge32", "Integer", "INTEGER", "Unsigned32", "TimeTicks"]
            
            if any(t in val_type for t in metric_types):
                if any(x in obj_name.lower() for x in ["index", "id", "name", "descr", "serial", "mac", "type", "version"]):
                    is_metric = False
                else:
                    is_metric = True

            if "TimeTicks" in val_type:
                ticks_match = re.search(r'\((\d+)\)', val_data)
                if ticks_match: val_data = int(ticks_match.group(1)) / 100.0
                is_metric = True

            if is_metric:
                try:
                    if "(" in str(val_data) and ")" in str(val_data):
                        val_data = re.search(r'\((\d+)\)', str(val_data)).group(1)
                    
                    clean_str = str(val_data).split()[0]
                    clean_val = float(clean_str)
                    if clean_val.is_integer(): clean_val = int(clean_val)
                    
                    parsed_data[index]["metrics"][obj_name] = {"value": clean_val, "module": module}
                except:
                    parsed_data[index]["labels"][obj_name] = val_data
            else:
                parsed_data[index]["labels"][obj_name] = val_data

        output_list = []
        current_time = int(time.time())

        for idx, entry in parsed_data.items():
            row_labels = entry["labels"]
            row_labels["snmp_index"] = entry["index"]
            
            for metric_name, metric_data in entry["metrics"].items():
                output_list.append({
                    "metric_name": metric_name,
                    "value": metric_data["value"],
                    "mib_module": metric_data["module"],
                    "metric_category": category,
                    "agent_host": target_host,
                    "timestamp": current_time,
                    "labels": row_labels.copy()
                })
        return output_list
