import numpy as np
import sys
import os

def extract_metadata(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    data = np.load(file_path)
    print(f"--- Metadata for {file_path} ---")
    print(f"Shape: {data.shape}")
    print(f"Dtype: {data.dtype}")
    print(f"Min:   {data.min()}")
    print(f"Max:   {data.max()}")
    print(f"Mean:  {data.mean()}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_metadata.py <path_to_npy_file>")
        sys.exit(1)
    extract_metadata(sys.argv[1])