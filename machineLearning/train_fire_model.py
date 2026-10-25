# train_fire_model.py
import tensorflow as tf
from tensorflow.keras import layers, models
import pandas as pd
from sklearn.model_selection import train_test_split
import numpy as np

def train_network():
    # 1. Load data parameters
    try:
        df = pd.read_csv("thermal_fire_dataset.csv")
    except FileNotFoundError:
        print("Error: thermal_fire_dataset.csv not found! Run generate_dataset.py first.")
        return

    X = df.drop(columns=['label']).values
    y = df['label'].values
    
    # Reshape unrolled lists back into 2D grid matrix blocks for the CNN
    X = X.reshape(-1, 24, 32, 1)
    
    # 2. Split data into training and validation pools (80/20)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 3. Build Convolutional Neural Network (CNN) matching project specs
    model = models.Sequential([
        layers.Conv2D(8, (3, 3), activation='relu', input_shape=(24, 32, 1)),
        layers.MaxPooling2D((2, 2)),
        layers.Conv2D(16, (3, 3), activation='relu'),
        layers.Flatten(),
        layers.Dense(16, activation='relu'),
        layers.Dense(1, activation='sigmoid') # Outputs classification score between 0.0 and 1.0
    ])
    
    model.compile(
        optimizer='adam',
        loss='binary_crossentropy',
        metrics=['accuracy']
    )
    
    print("\nCommencing Model Training Execution Pipeline...")
    model.fit(
        X_train, y_train,
        epochs=8,
        batch_size=16,
        validation_data=(X_test, y_test)
    )
    
    # 4. Save your finalized weights file match target signature
    model.save("fire_model.h5")
    print("\nSuccess! fire_model.h5 has been generated successfully in your folder.")

if __name__ == "__main__":
    train_network()

