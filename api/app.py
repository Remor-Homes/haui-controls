from dbm import error

from flask import Flask, request, jsonify
import subprocess
import os
import shutil


app = Flask(__name__)

env_path = "/home/haui/fpos_mqtt_ha/.env"
    
@app.route('/api/scan-wifi', methods=['GET'])
def scan_wifi():
    try:
        # Use nmcli to scan for available WiFi networks
        result = run_command("sudo nmcli -t -f ssid dev wifi")
        if not result['success']:
            return jsonify({'status': False, 'message': 'Failed to scan WiFi networks', 'stderr': result.get('stderr', '')}), 500
        # Split output into lines, filter out empty SSIDs
        ssids = [line for line in result['stdout'].split('\n') if line.strip()]
        # Remove duplicates while preserving order
        seen = set()
        unique_ssids = []
        for ssid in ssids:
            if ssid not in seen:
                seen.add(ssid)
                unique_ssids.append(ssid)
        return jsonify({'status': True, 'ssids': unique_ssids})
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/reboot', methods=['GET'])
def reboot_system():
    try:
        subprocess.run("sudo reboot", shell=True)
    except Exception as e:
        print(f"Error rebooting system: {e}")
        return jsonify(result=f'Error rebooting system: {e}'), 500
    
    return jsonify(result='Reboot command issued')

@app.route('/api/check-wifi-status', methods=['GET'])
def check_wifi_status():
    # Get current connected SSID (best effort)
    current_ssid = ""
    try:
        # Primary: nmcli (works well when NetworkManager is managing the connection)
        executed_command_1 = "sudo nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d: -f2"
        nm_result = run_command(executed_command_1)
        result_command_1 = f"Success: {nm_result['success']}, Stdout: {nm_result['stdout']}, Stderr: {nm_result['stderr']}"
        if nm_result['success'] and nm_result['stdout']:
            current_ssid = nm_result['stdout'].strip()

        # Fallback: iw (more reliable on some FullPageOS / wpa_supplicant setups)
        if not current_ssid:
            executed_command_2 = "sudo iw dev wlan0 link | grep SSID"
            iw_result = run_command(executed_command_2)
            result_command_2 = f"Success: {iw_result['success']}, Stdout: {iw_result['stdout']}, Stderr: {iw_result['stderr']}"
            if iw_result['success'] and iw_result['stdout']:
                current_ssid = iw_result['stdout'].split('SSID:')[-1].strip()
        else:
            executed_command_2 = "Command not executed since SSID was found with nmcli"
            result_command_2 = "N/A"
        
        executed_command_3 = "sudo nmcli device status | grep wlan0"
        wlan_status = run_command(executed_command_3)['stdout']
        result_command_3 = f"Success: {wlan_status is not None}, Stdout: {wlan_status}, Stderr: N/A"

        executed_command_4 = "sudo nmcli connection show --active"
        active_connections = run_command(executed_command_4)['stdout']
        result_command_4 = f"Success: {active_connections is not None}, Stdout: {active_connections}, Stderr: N/A"

        debug = {
            'executed_command_1': executed_command_1,
            'result_command_1': result_command_1,
            'executed_command_2': executed_command_2,
            'result_command_2': result_command_2,
            'executed_command_3': executed_command_3,
            'result_command_3': result_command_3,
            'executed_command_4': executed_command_4,
            'result_command_4': result_command_4,
            'connected': bool(current_ssid),
            'current_connected_ssid': current_ssid,
            'current_connections': active_connections,
            'wlan0_status': wlan_status,
        }
        return jsonify(debug), 200

    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

# New endpoint for restarting WiFi
@app.route('/api/restart-wifi', methods=['POST'])
def restart_wifi():
    try:
        debug_log = ["=== WiFi Restart Debug Log ==="]
        # Bring down and up the preconfigured connection
        debug_log.append("Bringing preconfigured down...")
        down_result = run_command("sudo nmcli connection down preconfigured")
        debug_log.append(f"Down: success={down_result['success']}, stdout={down_result['stdout']}, stderr={down_result['stderr']}")

        debug_log.append("Bringing preconfigured up...")
        up_result = run_command("sudo nmcli connection up preconfigured")
        debug_log.append(f"Up: success={up_result['success']}, stdout={up_result['stdout']}, stderr={up_result['stderr']}")

        if up_result['success']:
            return jsonify({'status': True, 'message': 'WiFi restarted'})
        else:
            return jsonify({'status': False, 'message': 'WiFi restart failed', 'debug': '\n'.join(debug_log)})
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/my_ip', methods=['GET'])
def get_my_ip():
    try:
        result = run_command("hostname -I | awk '{print $1}'")
        if result['success']:
            return jsonify({'ip': result['stdout'].strip()}), 200
        else:
            return jsonify({'status': False, 'message': 'Failed to retrieve IP address'}), 500
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/save-wifi', methods=['POST'])
def save_wifi():
    try:
        debug_log = ["=== WiFi Change Debug Log ==="]

        data = request.get_json(silent=True) or {}
        ssid = (data.get('ssid') or '').strip()
        password = (data.get('password') or '').strip()

        debug_log.append(f"Received SSID: '{ssid}', Password: {password if password else '(empty)'}")

        if not ssid:
            return jsonify({'status': False, 'message': 'SSID is required'}), 400

        # First, bring down the connection to ensure changes can be applied cleanly       
        debug_log.append("Bringing preconfigured down...")
        down_result = run_command("sudo nmcli connection down preconfigured")
        debug_log.append(f"Down: success={down_result['success']}, stdout={down_result['stdout']}, stderr={down_result['stderr']}")

        # Modify SSID and password only
        debug_log.append("Modifying preconfigured connection...")
        mod_cmd = f"sudo nmcli connection modify preconfigured wifi.ssid '{ssid}'"
        if password:
            mod_cmd += f" wifi-sec.psk '{password}'"
        mod_result = run_command(mod_cmd)
        debug_log.append(f"Modify: success={mod_result['success']}, stdout={mod_result['stdout']}, stderr={mod_result['stderr']}")

        # Check current saved SSID
        debug_log.append("Checking saved SSID to confirm the update...")
        check_cmd = "sudo nmcli -g 802-11-wireless.ssid connection show preconfigured"
        check_result = run_command(check_cmd)
        debug_log.append(f"Check SSID: success={check_result['success']}, stdout={check_result['stdout']}, stderr={check_result['stderr']}")
        current_ssid = check_result['stdout'].strip() if check_result['success'] else ''
        success = (current_ssid == ssid)

        # Finally, bring the connection back up
        debug_log.append("Bringing preconfigured up...")
        up_result = run_command("sudo nmcli connection up preconfigured")
        if 'error' in up_result:
            debug_log.append(f"Error bringing connection up: {up_result['error']}")
        else:
            debug_log.append(f"Up: success={up_result['success']}, stdout={up_result['stdout']}, stderr={up_result['stderr']}")

        if success:
            return jsonify(
                {
                    'status': True, 
                    'message': 'WiFi settings applied', 
                    'debug': '\n'.join(debug_log)
                    }
            )
        else:
            return jsonify(
                {
                    'status': False, 
                    'message': f'WiFi SSID update failed', 
                    'debug': '\n'.join(debug_log)
                }
            )
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/get-hostname', methods=['GET'])
def get_hostname():
    try:
        result = run_command("hostname")
        if result['success']:
            return jsonify({'hostname': result['stdout'].strip()}), 200
        else:
            return jsonify({'status': False, 'message': 'Failed to retrieve hostname'}), 500
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/set-hostname', methods=['POST'])
def set_hostname():
    try:
        data = request.get_json(silent=True) or {}
        new_hostname = (data.get('hostname') or '').strip()

        if not new_hostname:
            return jsonify({'status': False, 'message': 'Hostname is required'}), 400

        if not new_hostname.replace('-', '').isalnum() or len(new_hostname) > 63:
            return jsonify({
                'status': False,
                'message': 'Hostname can only contain letters, numbers, and hyphens (max 63 chars)'
            }), 400

        debug_log = ["=== Hostname Change Debug ==="]
        debug_log.append(f"Target hostname: {new_hostname}")

        # 1. First, temporarily add the new hostname to /etc/hosts to avoid sudo resolution error
        debug_log.append("Temporarily updating /etc/hosts to prevent sudo resolution error...")
        current_hosts = ""
        try:
            with open('/etc/hosts', 'r') as f:
                current_hosts = f.read()
        except:
            pass

        # Add new hostname alongside old one
        temp_hosts = current_hosts.strip() + f"\n127.0.1.1   {new_hostname}\n"
        run_command(f"echo '{temp_hosts}' | sudo tee /etc/hosts > /dev/null")

        # 2. Now safely set the hostname with hostnamectl
        debug_log.append("Setting hostname with hostnamectl...")
        result = run_command(f"sudo hostnamectl set-hostname {new_hostname}")
        if not result['success']:
            debug_log.append(f"hostnamectl failed: {result.get('stderr', '')}")
            return jsonify({
                'status': False,
                'message': 'Failed to set hostname with hostnamectl',
                'debug': '\n'.join(debug_log)
            }), 500

        # 3. Final clean /etc/hosts (remove old hostname if present)
        debug_log.append("Writing final clean /etc/hosts...")
        final_hosts = f"""127.0.0.1   localhost
::1         localhost ip6-localhost ip6-loopback
ff02::1     ip6-allnodes
ff02::2     ip6-allrouters
127.0.1.1   {new_hostname}
"""
        run_command(f"echo '{final_hosts}' | sudo tee /etc/hosts > /dev/null")

        # 4. Clear Chromium locks (prevents stuck logo)
        debug_log.append("Clearing Chromium profile locks...")
        run_command("rm -rf /home/haui/.config/chromium/Singleton*")
        run_command("rm -f /home/haui/.config/chromium/Default/.org.chromium.Chromium.*")

        debug_log.append("Hostname change completed successfully")

        return jsonify({
            'status': True,
            'message': f'Hostname successfully changed to "{new_hostname}". A reboot is required.',
            'debug': '\n'.join(debug_log)
        })

    except Exception as e:
        return jsonify({
            'status': False,
            'message': f'Unexpected error: {str(e)}'
        }), 500

@app.route('/api/reset-main-url', methods=['GET'])
def reset_main_url():
    try:
        run_command(f"echo 'http://localhost/haui-wizard' | sudo tee /boot/firmware/fullpageos.txt > /dev/null")
        return jsonify({'status': True, 'message': 'Main URL reset successfully'})
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/get-main-url', methods=['GET'])
def get_main_url():
    try:
        with open('/boot/firmware/fullpageos.txt', 'r') as f:
            main_url = f.readline().strip()
        return jsonify({'status': True, 'main_url': main_url}), 200
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/cleanup-chromium-locks', methods=['POST'])
def cleanup_chromium_locks():
    try:
        run_command("rm -rf /home/haui/.config/chromium/Singleton*")
        run_command("rm -f /home/haui/.config/chromium/Default/.org.chromium.Chromium.*")
        return jsonify({'status': True, 'message': 'Chromium locks cleaned up successfully'})
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/set-main-url', methods=['POST'])
def set_main_url():
    try:
        data = request.get_json(silent=True) or {}
        main_url = (data.get('main_url') or '').strip()

        if not main_url:
            return jsonify({'status': False, 'message': 'Main URL is required'}), 400

        # Write the main URL to /boot/firmware/fullpageos.txt
        try:
            run_command(f"echo '{main_url}' | sudo tee /boot/firmware/fullpageos.txt > /dev/null")
        except Exception as file_err:
            return jsonify({'status': False, 'message': f'Failed to write to file: {file_err}'}), 500

        return jsonify({'status': True, 'message': 'Main URL updated successfully'})
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500
    
@app.route('/api/save-mqtt-server', methods=['POST'])
def save_mqtt_server():
    try:
        data = request.get_json(silent=True) or {}
        mqtt_server = (data.get('mqtt_server') or '').strip()

        if not mqtt_server:
            return jsonify({'status': False, 'message': 'MQTT Server is required'}), 400

        # Write the MQTT server to /boot/firmware/mqtt_server.txt
        try:
            run_command(f"echo '{mqtt_server}' | sudo tee /boot/firmware/mqtt_server.txt > /dev/null")
        except Exception as file_err:
            return jsonify({'status': False, 'message': f'Failed to write to file: {file_err}'}), 500

        return jsonify({'status': True, 'message': 'MQTT Server updated successfully'})
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/set-mqtt-cert', methods=['POST'])
def set_mqtt_cert():
    try:
        server = get_mqtt_server()
        if ':' in server:  # Just to confirm we can read the MQTT server before accepting cert upload
            try:
                server = server.split(':')
                port = server[1]
                server = server[0]
            except Exception as e:
                return jsonify({'status': False, 'message': f'Invalid MQTT server format: {e}'}), 400
        else:
            port = '8883'  # Default MQTT TLS port

        if 'cert_file' not in request.files:
            return jsonify({'status': False, 'message': 'No certificate file uploaded'}), 400

        try:
            file = request.files['cert_file']
            if file.filename == '':
                return jsonify({'status': False, 'message': 'No selected file'}), 400
        except Exception as file_err:
            return jsonify({'status': False, 'message': f'Error processing file upload: {file_err}'}), 400

        # Save the certificate
        try:
            temp_path = '/tmp-remorh/ca.crt'
            file.save(temp_path)
        except Exception as file_err:
            return jsonify({'status': False, 'message': f'Error saving certificate: {file_err}'}), 500

        mqtt_env = f"""BROKER_IP={server}
BROKER_USERNAME=user
BROKER_PASSWORD=pass
BROKER_PORT={port}
DISPLAY_NAME=10-0045
DIMMING_TO_OFF_SECONDS='11'
DIMMING_PERCENT='19'
LAST_TIMEOUT_SET='60'
DISPLAY_DEVICE_NAME=ft5x06
"""

        # write the .env with the data required.
        try:
            run_command(f"echo '{mqtt_env}' | sudo tee {env_path} > /dev/null")
        except Exception as file_err:
            return jsonify({'status': False, 'message': f'Failed to write to file: {file_err}'}), 500

        return jsonify({'status': True, 'message': 'MQTT Certificate updated successfully'})
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500
    
@app.route('/api/set-mqtt-credentials', methods=['POST'])
def set_mqtt_credentials():
    try:
        server = get_mqtt_server()
        if ':' in server:  # Just to confirm we can read the MQTT server before accepting cert upload
            try:
                server = server.split(':')
                port = server[1]
                server = server[0]
            except Exception as e:
                return jsonify({'status': False, 'message': f'Invalid MQTT server format: {e}'}), 400
        else:
            port = '8883'  # Default MQTT TLS port

        data = request.get_json(silent=True) or {}
        mqtt_username = (data.get('mqtt_username') or '').strip()
        mqtt_password = (data.get('mqtt_password') or '').strip()

        if not mqtt_username or not mqtt_password:
            return jsonify({'status': False, 'message': 'MQTT Username and Password are required'}), 400

        mqtt_env = f"""BROKER_IP={server}
BROKER_USERNAME={mqtt_username}
BROKER_PASSWORD={mqtt_password}
BROKER_PORT={port}
DISPLAY_NAME=10-0045
DIMMING_TO_OFF_SECONDS='11'
DIMMING_PERCENT='19'
LAST_TIMEOUT_SET='60'
DISPLAY_DEVICE_NAME=ft5x06
"""

        # write the .env with the data required.
        try:
            run_command(f"echo '{mqtt_env}' | sudo tee {env_path} > /dev/null")
        except Exception as file_err:
            return jsonify({'status': False, 'message': f'Failed to write to file: {file_err}'}), 500

        return jsonify({'status': True, 'message': 'MQTT Server updated successfully'})
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/check-backlight-service', methods=['GET'])
def check_backlight_service():
    try:
        result = run_command('sudo systemctl is-active backlight.service')
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/enable-backlight-service', methods=['POST'])
def enable_backlight_service():
    try:
        result = create_service_for_backlight_script()
        return jsonify(result), 200 if result['status'] else 500
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

@app.route('/api/set-backlight-level', methods=['POST'])
def set_backlight_level():
    try:
        # Read-only access to .env file to get DISPLAY_NAME
        display_name = "10-0045"
        return_message = ""
        try:
            with open(env_path, 'r') as f:  # read-only mode
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        if key.strip() == 'DISPLAY_NAME':
                            display_name = value.strip().strip('"\'')
                            break
        except Exception as file_err:
            return_message += f"Error reading .env file: {file_err}"

        data = request.get_json(silent=True) or {}
        level = data.get('level')
        if level is None:
            return_message += 'Backlight level is required'
            return jsonify({'status': False, 'message': return_message}), 400

        cmd = f"echo {level} | sudo tee /sys/class/backlight/{display_name}/brightness > /dev/null"
        try:
            subprocess.call(cmd, shell=True)
        except Exception as e:
            jsonify({'status': False, 'message': return_message}), 400

        return jsonify({'status': True, 'message': return_message}), 200
    except Exception as e:
        return jsonify({'status': False, 'message': str(e)}), 500

def get_mqtt_server():
    try:
        with open('/boot/firmware/mqtt_server.txt', 'r') as f:
            mqtt_server = f.readline().strip()
        return mqtt_server
    except Exception as e:
        return "Unknown:8883"
    
def get_hostname():
    try:
        result = run_command("hostname")
        if result['success']:
            return result['stdout'].strip()
        else:
            return "Unknown"
    except Exception as e:
        return "Unknown"

def run_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout.strip(),
            'stderr': result.stderr.strip(),
            'returncode': result.returncode
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def create_service_for_backlight_script():
    service_src = '/home/haui/fpos_mqtt_ha/systemctl/backlight.service'
    service_dst = '/etc/systemd/backlight.service'
    result_log = []

    # Reload systemd
    reload_result = run_command('sudo systemctl daemon-reload')
    result_log.append(f"daemon-reload: success={reload_result['success']}, stderr={reload_result['stderr']}")
    if not reload_result['success']:
        return {'status': False, 'message': 'Failed to reload systemd', 'debug': result_log}

    # Enable the service
    enable_result = run_command('sudo systemctl enable backlight.service')
    result_log.append(f"enable: success={enable_result['success']}, stderr={enable_result['stderr']}")
    if not enable_result['success']:
        return {'status': False, 'message': 'Failed to enable service', 'debug': result_log}

    # Start the service
    start_result = run_command('sudo systemctl start backlight.service')
    result_log.append(f"start: success={start_result['success']}, stderr={start_result['stderr']}")
    if not start_result['success']:
        return {'status': False, 'message': 'Failed to start service', 'debug': result_log}

    # Check status
    status_result = run_command('sudo systemctl is-active backlight.service')
    result_log.append(f"status: stdout={status_result['stdout']}, success={status_result['success']}")
    if status_result['stdout'].strip() == 'active':
        return {'status': True, 'message': 'Service is running as expected', 'debug': result_log}
    else:
        return {'status': False, 'message': 'Service is not running', 'debug': result_log}

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=5000)
