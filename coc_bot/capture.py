import subprocess
import time
from datetime import datetime
import os

def capture_high_res():
    # Make sure folder exists
    os.makedirs("coc_bot/logs/debug", exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"coc_bot/logs/debug/screen_{timestamp}.png"
    
    print("Waking screen and launching game...")
    # Wake
    subprocess.run(['adb', 'shell', 'input', 'keyevent', '26'])
    time.sleep(1)
    
    # Launch
    subprocess.run(['adb', 'shell', 'monkey', '-p', 'com.supercell.clashofclans', '-c', 'android.intent.category.LAUNCHER', '1'], capture_output=True)
    
    print("Waiting 15 seconds for game to load fully...")
    time.sleep(15)
    
    print(f"Capturing screen to {filename}...")
    # Pull raw PNG
    with open(filename, "wb") as f:
        pipe = subprocess.Popen(['adb', 'exec-out', 'screencap', '-p'], stdout=f)
        pipe.communicate()
        
    print(f"Done! Open {filename} in an image editor.")
    print("Crop the buttons/buildings and save them as PNGs in:")
    print("  coc_bot/assets/buttons/")
    print("  coc_bot/assets/buildings/")

if __name__ == "__main__":
    capture_high_res()
