# compile_agent.py
import os
import sys
import cloudpickle

# FIXED: Added the required 'os' and 'sys' imports above so this line executes
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

try:
    # Pull the live root object directly from your configuration file
    from agent import root_agent
    
    output_filename = "agent.pkl"
    
    print(f"Serializing '{root_agent.name}' targeting framework instance layout...")
    
    with open(output_filename, "wb") as f:
        cloudpickle.dump(root_agent, f)
        
    print(f" SUCCESS: '{output_filename}' generated cleanly in local workspace directory.")
    
except ImportError as ie:
    print(f" IMPORT ERROR: Verification failed. Ensure agent.py exists in this directory. Details: {ie}")
except Exception as e:
    print(f" ERROR: Serialization failed: {str(e)}")