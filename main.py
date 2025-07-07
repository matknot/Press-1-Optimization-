from flask import Flask, request, render_template, jsonify
import math

app = Flask(__name__, template_folder='templates')

# Constants
BILLET_AREA_M2 = 0.0507  # Converted from 78.54 in²
SPEED_FACTOR = 0.69      # From 69% puller speed
PSI_TO_PA = 6894.76      # Conversion factor
GRAVITY = 9.81           # N/kgf conversion
LN_MIN = math.log(5.0)   # Low ratio (5:1)
LN_MAX = math.log(100.0) # High ratio (100:1)
RAMP_MIN = 1.0           # Minimum ramp input (1% of 10 s)
RAMP_MAX = 100.0         # Maximum ramp input (100% of 10 s)
RATIO_MIN = 5.0          # Minimum ratio
RATIO_MAX = 100.0        # Maximum ratio
MAX_SPEED = 13.0         # Realistic max speed for your press (m/min)
MAX_FORCE = 190.0        # Hard cap for puller force (kgf)
K_RUNOUT = 0.0015        # Run-out factor (kgf/m per cavity)
K_BASE = 0.1             # Baseline torque factor
K_ACCEL = 0.1            # Acceleration torque factor

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        # Get and validate inputs
        ratio = request.form.get('ratio')
        if not ratio or ratio.strip() == '':
            return jsonify({'error': 'Ratio is required'})
        ratio = float(ratio)

        runout = float(request.form.get('run_out', 0.0))  # Optional
        set_speed = float(request.form.get('setpoint', 0.0))  # Optional
        cavities = int(request.form.get('cavities', 1))  # Default to 1
        cavities = max(1, min(4, cavities))  # Limit to 1-4

        # Calculations
        ln_ratio = math.log(ratio)
        burp_psi = 100.0 * ln_ratio + 10.0 * 78.54
        burp_pa = burp_psi * PSI_TO_PA
        extruded_area = BILLET_AREA_M2 / ratio
        profile_speed_percent = min(set_speed / 0.13, MAX_SPEED / 0.13) if set_speed > 0 else 0

        # Calculate ramp input (1-100) based on process factors
        initial_puller_force = 164.0  # Initial estimate to break circular reference
        ramp_input = RAMP_MIN + (RAMP_MAX - RAMP_MIN) * ((ln_ratio - math.log(RATIO_MIN)) / (math.log(RATIO_MAX) - math.log(RATIO_MIN))) * (initial_puller_force / MAX_FORCE) * (MAX_SPEED / set_speed) if set_speed > 0 else RAMP_MIN
        ramp_input = max(RAMP_MIN, min(RAMP_MAX, ramp_input))  # Constrain to 1-100
        ramp_time = ramp_input / 10  # Convert to seconds (0.1-10.0 s)

        # Torque with acceleration
        torque = K_BASE + K_ACCEL * initial_puller_force * set_speed * (10 / ramp_time) if set_speed > 0 else K_BASE

        # Recalculate with actual puller force for accuracy
        base_force_n = burp_pa * extruded_area * cavities * SPEED_FACTOR
        base_force_kgf = base_force_n / GRAVITY
        k_min = 50.0 / base_force_kgf
        k_max = 190.0 / base_force_kgf
        interp_factor = (ln_ratio - LN_MIN) / (LN_MAX - LN_MIN)
        k = k_min + (k_max - k_min) * interp_factor
        puller_force_base = k * base_force_n / GRAVITY
        puller_force_total = puller_force_base * (1 + K_RUNOUT * runout * cavities)
        puller_force_final = min(MAX_FORCE, puller_force_total)

        # Recalculate ramp_input with actual puller_force
        ramp_input = RAMP_MIN + (RAMP_MAX - RAMP_MIN) * ((ln_ratio - math.log(RATIO_MIN)) / (math.log(RATIO_MAX) - math.log(RATIO_MIN))) * (puller_force_final / MAX_FORCE) * (MAX_SPEED / set_speed) if set_speed > 0 else RAMP_MIN
        ramp_input = max(RAMP_MIN, min(RAMP_MAX, ramp_input))
        ramp_time = ramp_input / 10  # Updated ramp time

        # Recalculate torque with actual puller_force
        torque = K_BASE + K_ACCEL * puller_force_final * set_speed * (10 / ramp_time) if set_speed > 0 else K_BASE
        torque_ramp_seconds = ramp_time  # Use calculated ramp time

        # Format outputs
        response = {
            'profile_speed': f"{int(profile_speed_percent)}% ({set_speed if set_speed > 0 else 0.0})" if set_speed > 0 else "0% (0.0)",
            'torque_ramp': f"{round(torque_ramp_seconds * 10)} ({torque_ramp_seconds:.1f}s)",
            'puller_force': round(puller_force_final),
            'burp_psi': int(burp_psi)
        }
        return jsonify(response)

    except ValueError:
        return jsonify({'error': 'Invalid input. Please enter numeric values.'})
    except Exception as e:
        return jsonify({'error': f'Calculation error: {str(e)}'})

@app.route('/clear', methods=['POST'])
def clear():
    return jsonify({})  # Clears form on client side

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)