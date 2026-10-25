# evaluate_model.py
import os
# Force TensorFlow to suppress underlying hardware optimization logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import tensorflow as tf
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix

def evaluate_system_model():
    print("Loading dataset and compiled model for verification testing...")
    
    try:
        df = pd.read_csv("thermal_fire_dataset.csv")
        model = tf.keras.models.load_model("fire_model.h5")
    except FileNotFoundError as e:
        print(f"File loading error: {e}")
        return

    X = df.drop(columns=['label']).values
    y = df['label'].values
    X = X.reshape(-1, 24, 32, 1)
    
    # Extract the exact same 20% test partition used during validation
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Run predictions
    raw_predictions = model.predict(X_test, verbose=0)
    
    # Target encoding check: FIRE if prediction confidence score <= 0.2
    y_pred = np.where(raw_predictions <= 0.2, 0, 1)
    
    # Extract structural matrix rates explicitly from confusion matrix
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
    
    # Mapping coordinates safely:
    # Row 0: True Fire (0) -> [True Fire, Missed Fire]
    # Row 1: True Natural (1) -> [False Alarm, True Natural]
    true_fire_correct = cm[0][0]
    missed_fire = cm[0][1]
    false_alarm = cm[1][0]
    true_natural_correct = cm[1][1]
    
    total_samples = len(y_test)
    total_correct = true_fire_correct + true_natural_correct
    
    # FIXED: Clear mathematical percentage calculations
    accuracy = (total_correct / total_samples) * 100.0
    
    total_actual_fires = true_fire_correct + missed_fire
    total_actual_naturals = false_alarm + true_natural_correct
    
    false_positive_rate = (false_alarm / total_actual_naturals) * 100.0 if total_actual_naturals > 0 else 0.0
    false_negative_rate = (missed_fire / total_actual_fires) * 100.0 if total_actual_fires > 0 else 0.0
    
    print("\n" + "="*50)
    print("  EARLY FIRE DETECTION MODEL EVALUATION REPORT (S1-S3)")
    print("="*50)
    print(f"Total Validation Test Samples Ingested : {total_samples}")
    print(f"Overall Classification Accuracy        : {accuracy:.2f}% (Target: >= 89%)")
    print(f"False-Positive Rate (False Alarm)      : {false_positive_rate:.2f}% (Target: <= 10%)")
    print(f"False-Negative Rate (Missed Fire)      : {false_negative_rate:.2f}% (Target: <= 5%)")
    print("-"*50)
    print("CONFUSION MATRIX MATRIX PLOT REFERENCE:")
    print("                  Predicted FIRE   |  Predicted NATURAL")
    print(f"Actual FIRE:       {true_fire_correct} (True Fire)   |  {missed_fire} (Missed Fire)")
    print(f"Actual NATURAL:    {false_alarm} (False Alarm) |  {true_natural_correct} (True Natural)")
    print("="*50)
    
    if accuracy >= 89.0 and false_positive_rate <= 10.0 and false_negative_rate <= 5.0:
        print("STATUS SUMMARY: ALL ML OBJECTIVE PERFORMANCES PASSED (OBJ03 MET)")
    else:
        print("STATUS SUMMARY: SPECIFICATION TARGET VARIANCE DETECTED")

if __name__ == "__main__":
    evaluate_system_model()
