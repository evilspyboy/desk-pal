#!/usr/bin/env python3
"""
Desk-Pal Hardware Switch Diagnostic (Live Automated Test)
Listens for 35 seconds or until all 6 switches have been pressed.
"""

import sys
import time
try:
    from gpiozero import Button
except ImportError:
    print("Skipping test_switches: gpiozero not available on non-Pi platform")
    sys.exit(0)

SWITCH_CONFIG = [
    {"id": 1, "pin_bcm": 0,  "phys_pin": 27, "color": "Brown", "name": "Switch 1", "gnd_pin": 25},
    {"id": 2, "pin_bcm": 5,  "phys_pin": 29, "color": "Brown", "name": "Switch 2", "gnd_pin": 25},
    {"id": 3, "pin_bcm": 6,  "phys_pin": 31, "color": "Brown", "name": "Switch 3", "gnd_pin": 25},
    {"id": 4, "pin_bcm": 13, "phys_pin": 33, "color": "Brown", "name": "Switch 4", "gnd_pin": 25},
    {"id": 5, "pin_bcm": 19, "phys_pin": 35, "color": "Brown", "name": "Switch 5", "gnd_pin": 39},
    {"id": 6, "pin_bcm": 26, "phys_pin": 37, "color": "Red",   "name": "Switch 6", "gnd_pin": 39},
]

print("=" * 65, flush=True)
print("      DESK-PAL MX SWITCH HARDWARE DIAGNOSTIC", flush=True)
print("=" * 65, flush=True)
print("Diagnostic window: 35 seconds.", flush=True)
print("Press each switch (from Left to Right, Red is SW 6 on the far right)!\n", flush=True)

buttons = {}
press_counts = {sw["id"]: 0 for sw in SWITCH_CONFIG}

for sw in SWITCH_CONFIG:
    sw_id = sw["id"]
    bcm = sw["pin_bcm"]
    try:
        btn = Button(bcm, pull_up=True, bounce_time=0.05)
        buttons[sw_id] = btn

        def make_press_handler(s):
            def handler():
                press_counts[s["id"]] += 1
                status = " | ".join(f"SW{i}:{'[X]' if b.is_pressed else '[ ]'}" for i, b in buttons.items())
                print(f"[PRESS]   SW{s['id']} ({s['color']:5s} | Pin {s['phys_pin']} / BCM {s['pin_bcm']:2d}) -> Count: {press_counts[s['id']]} | State: {status}", flush=True)
            return handler

        def make_release_handler(s):
            def handler():
                print(f"[RELEASE] SW{s['id']} ({s['color']:5s})", flush=True)
            return handler

        btn.when_pressed = make_press_handler(sw)
        btn.when_released = make_release_handler(sw)
        print(f"  Initialized SW{sw_id}: Pin {sw['phys_pin']} (BCM {bcm:2d}) [{sw['color']}]", flush=True)
    except Exception as e:
        print(f"  [ERROR] Could not initialize SW{sw_id} (BCM {bcm}): {e}", flush=True)

print("\n>>> LISTENING NOW: Please press your switches in order (1 -> 6)... <<<\n", flush=True)

start_time = time.time()
timeout = 35

try:
    while time.time() - start_time < timeout:
        time.sleep(0.2)
        # If all 6 have at least 1 press, give an extra 3 seconds then stop
        if all(press_counts[sw["id"]] > 0 for sw in SWITCH_CONFIG):
            print("\n*** All 6 switches detected at least once! Finishing in 3s... ***", flush=True)
            time.sleep(3)
            break
except KeyboardInterrupt:
    pass

print("\n" + "=" * 65, flush=True)
print("                  DIAGNOSTIC TEST SUMMARY", flush=True)
print("=" * 65, flush=True)
passed = 0
for sw in SWITCH_CONFIG:
    count = press_counts.get(sw["id"], 0)
    if count > 0:
        result = "[PASS - WORKING]"
        passed += 1
    else:
        result = "[FAIL - NO SIGNAL]"
    print(f"  SW{sw['id']} ({sw['color']:5s} | Pin {sw['phys_pin']} / BCM {sw['pin_bcm']:2d}): {count:2d} presses -> {result}", flush=True)

print("-" * 65, flush=True)
print(f"Result: {passed}/6 switches verified.", flush=True)
print("=" * 65, flush=True)
