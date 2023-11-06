import requests
import re
import os

buckets = ["Bucket1", "Bucket2"]
url = "https://storage.googleapis.com/"
output_file = "GCP-Bucket-Scraper.txt"

extension_count = {}  # Dictionary to count file extensions

with open(output_file, 'w') as file:  # Open the output file in write mode
    for bucket in buckets:
        response = requests.get(url + bucket)
        if response.status_code == 200:
            data = response.text

            # Use regular expressions to extract content between <Key> and </Key> tags and between <Size> and </Size> tags
            key_pattern = re.compile(r'<Key>(.*?)<\/Key>')
            size_pattern = re.compile(r'<Size>(.*?)<\/Size>')
            keys = key_pattern.findall(data)
            sizes = size_pattern.findall(data)

            for key, size in zip(keys, sizes):
                # Convert size to megabytes
                size_mb = int(size) / (1024 * 1024)
                file.write(f"Bucket: {bucket}, File: {key}, Size: {size_mb:.2f} MB\n")
                print(f"Bucket: {bucket}, File: {key}, Size: {size_mb:.2f} MB\n")

            # Count file extensions
            for key in keys:
                _, file_extension = os.path.splitext(key)
                if file_extension:
                    extension_count[file_extension] = extension_count.get(file_extension, 0) + 1
        else:
            print(f"Failed to fetch data for {bucket}. Status code:", response.status_code)

    # Print file extension statistics across all buckets
    file.write("\nFile Extension Statistics Across All Buckets:\n")
    for extension, count in extension_count.items():
        file.write(f"Extension: {extension}, Count: {count}\n")
        print(f"Extension: {extension}, Count: {count}\n")

print(f"Output saved to {output_file}")
