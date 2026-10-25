# generate_dataset.py
import numpy as np
import pandas as pd
import config

np.random.seed(42)

def generate_thermal_dataset(num_samples=1000):
    data = []
    labels = []
    
    print("Generating synthetic thermal grid patterns...")
    for _ in range(num_samples):
        # 50% chance to generate a Normal/Natural baseline frame
        if np.random.rand() > 0.5:
            # Normal background room temperature fluctuates around 24 degrees
            frame = np.random.normal(loc=24.0, scale=2.0, size=(24, 32))
            labels.append(1)  # Natural = 1
        else:
            # Fire frame: baseline room temp + a hot localized plume
            frame = np.random.normal(loc=25.0, scale=2.0, size=(24, 32))
            
            # Choose target epicenter coordinates away from the absolute edges
            fire_y = np.random.randint(4, 20)
            fire_x = np.random.randint(4, 28)
            
            # Inject structural high-heat signature exceeding config.TEMP_FIRE_C
            frame[fire_y, fire_x] = np.random.uniform(70.0, 110.0)      
            # Simulate spatial thermal dissipation behavior into adjacent pixels
            frame[fire_y-1:fire_y+2, fire_x-1:fire_x+2] += np.random.uniform(25.0, 45.0) 
            
            labels.append(0)  # Fire = 0
            
        data.append(frame.flatten())
        
    columns = [f"pixel_{i}" for i in range(768)]
    df = pd.DataFrame(data, columns=columns)
    df['label'] = labels
    
    df.to_csv("thermal_fire_dataset.csv", index=False)
    print("Successfully generated thermal_fire_dataset.csv with 1000 samples.")

if __name__ == "__main__":
    generate_thermal_dataset()
