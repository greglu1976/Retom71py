import comtypes.client
import os

# 1. Specify the path to the RetomDriver DLL or TLB file.
#    You need to find where RetomDriver.dll is installed on your PC.
#    Common paths might be:
#    "C:\\Program Files\\Retom\\RetomDriver.dll" 
#    or wherever your vendor installed it.
TLB_PATH = r"RTDI.tlb"  # <--- CHANGE THIS PATH

if not os.path.exists(TLB_PATH):
    raise FileNotFoundError(f"Could not find RetomDriver at: {TLB_PATH}")

print(f"Generating wrapper for: {TLB_PATH}")

try:
    # This command reads the TLB/DLL and generates Python files 
    # in the comtypes/gen folder
    comtypes.client.GetModule(TLB_PATH)
    print("Success! Wrapper generated.")
    print("Check the folder: C:\\WWW\\pyretom\\venv\\Lib\\site-packages\\comtypes\\gen")
except Exception as e:
    print(f"Error generating wrapper: {e}")