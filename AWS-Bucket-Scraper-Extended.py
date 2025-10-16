###
### Author: Jordon Lovik 
### Jordon@loviksecurity.com
###
### AWS Public S3 Bucket Scanner
### 
### This script scans public AWS S3 buckets and generates detailed reports
### of their contents, including URL-encoded links and file extension statistics.
###
### USAGE:
###
### 1. Using the default bucket list defined in the script:
###    python script.py
###
### 2. Scanning a single bucket (auto-detect region):
###    python script.py my-public-bucket
###
### 3. Scanning a single bucket with explicit region:
###    python script.py my-public-bucket us-east-1
###
### 4. Scanning multiple buckets (auto-detect regions):
###    python script.py bucket1 bucket2 bucket3
###
### 5. Scanning multiple buckets with explicit regions:
###    python script.py bucket1 us-east-1 bucket2 us-west-2
###
### 6. Mixed mode - some with regions, some without:
###    python script.py bucket1 bucket2 us-west-2 bucket3 bucket4 eu-central-1
###
### 7. Combining multiple buckets into a single output file:
###    python script.py --combine bucket1 bucket2 bucket3
###    python script.py --combine bucket1 us-east-1 bucket2 us-west-2
###
### 8. Buckets with dots in the name:
###    python script.py demo.enter.com
###    python script.py my.bucket.name us-east-1
###
### Command-line format: [--combine] bucket_name [region] [bucket_name [region] ...]
### - Bucket names can be provided alone (region will be auto-detected)
### - Or provide bucket_name region pairs for explicit region specification
### - You can mix both styles in the same command
### - Use --combine flag to output all results to a single JSON file
### - Bucket names with dots are fully supported
###
### OUTPUT:
### - Without --combine: Creates separate JSON files for each bucket scanned
### - With --combine: Creates a single JSON file containing all bucket results
###   - Includes per-bucket extension statistics
###   - Includes global extension statistics across all buckets
### - Output filename format: BucketName_YYYYMMDD_HHMMSS.json (or Combined_YYYYMMDD_HHMMSS.json)
### - Files include bucket name, region, URL-encoded links, file sizes, and extension statistics
### - Extension statistics are sorted by count (most common first)
###
### EXAMPLES:
### python script.py company-data-bucket
### python script.py bucket1 bucket2 bucket3
### python script.py logs-bucket us-west-2 backups-bucket
### python script.py bucket1 bucket2 us-west-2 bucket3 eu-west-1 bucket4
### python script.py --combine bucket1 bucket2 bucket3
### python script.py --combine bucket1 us-east-1 bucket2 us-west-2
### python script.py demo.enter.com my.bucket.name
###

import boto3
import botocore
import os
import sys
import json
import requests
from urllib.parse import quote
from datetime import datetime

# Default list of public S3 buckets along with their regions
# This will be used if no command-line arguments are provided
# Region can be None to auto-detect
public_buckets = [
    ("Bucket1", None),  # Auto-detect region
    ("Bucket2", "us-west-2"),  # Explicit region
    ("Bucket3", None)  # Auto-detect region
]

def bucket_has_dots(bucket_name):
    """
    Check if a bucket name contains dots.
    Buckets with dots require path-style URLs instead of virtual-hosted style.
    """
    return '.' in bucket_name

def get_bucket_url(bucket_name, region=None):
    """
    Get the appropriate S3 URL for a bucket.
    - Buckets with dots use path-style: https://s3.region.amazonaws.com/bucket-name
    - Buckets without dots use virtual-hosted style: https://bucket-name.s3.amazonaws.com
    """
    if bucket_has_dots(bucket_name):
        # Path-style URL
        if region and region != 'us-east-1':
            return f"https://s3.{region}.amazonaws.com/{bucket_name}"
        else:
            return f"https://s3.amazonaws.com/{bucket_name}"
    else:
        # Virtual-hosted style URL
        return f"https://{bucket_name}.s3.amazonaws.com"

def get_bucket_region(bucket_name):
    """
    Automatically detect the region of an S3 bucket using multiple methods.
    Returns the region name or None if detection fails.
    """
    print(f"  Attempting to detect region for '{bucket_name}'...")
    
    # Method 1: Try using HTTP HEAD request to detect region from headers
    try:
        url = get_bucket_url(bucket_name)
        response = requests.head(url, allow_redirects=False, timeout=10)
        
        # Check for x-amz-bucket-region header
        if 'x-amz-bucket-region' in response.headers:
            region = response.headers['x-amz-bucket-region']
            print(f"  ✓ Auto-detected region for bucket '{bucket_name}': {region} (via HTTP headers)")
            return region
        
        # Check for redirect location
        if response.status_code in [301, 302, 307] and 'Location' in response.headers:
            location = response.headers['Location']
            # Extract region from redirect URL
            # Can be: https://bucket.s3.eu-west-2.amazonaws.com/ or https://s3.eu-west-2.amazonaws.com/bucket
            if '.s3.' in location and '.amazonaws.com' in location:
                parts = location.split('.s3.')[1].split('.amazonaws.com')[0]
                if parts and parts != 'amazonaws':  # not a redirect to standard endpoint
                    print(f"  ✓ Auto-detected region for bucket '{bucket_name}': {parts} (via redirect)")
                    return parts
            elif 's3.' in location and '.amazonaws.com' in location:
                # Handle path-style redirects like https://s3.eu-west-2.amazonaws.com/bucket
                match = location.split('s3.')[1].split('.amazonaws.com')[0]
                if match and match != 'amazonaws':
                    print(f"  ✓ Auto-detected region for bucket '{bucket_name}': {match} (via redirect)")
                    return match
    except requests.RequestException as e:
        print(f"  ✗ HTTP HEAD method failed for '{bucket_name}': {e}")
    
    # Method 2: Try get_bucket_location API
    try:
        session = boto3.Session()
        config = botocore.config.Config(signature_version=botocore.UNSIGNED)
        s3 = session.client('s3', region_name='us-east-1', config=config)
        
        response = s3.get_bucket_location(Bucket=bucket_name)
        region = response['LocationConstraint']
        if region is None:
            region = 'us-east-1'
        
        print(f"  ✓ Auto-detected region for bucket '{bucket_name}': {region} (via get_bucket_location)")
        return region
        
    except botocore.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            print(f"  ✗ Error: Bucket '{bucket_name}' does not exist")
            return None
        else:
            print(f"  ✗ get_bucket_location failed for '{bucket_name}': {error_code}")
    except Exception as e:
        print(f"  ✗ Unexpected error with get_bucket_location for '{bucket_name}': {e}")
    
    # Method 3: Try using GetBucketLocation with a request that forces region info
    try:
        url = f"{get_bucket_url(bucket_name)}?location"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            # Parse the XML response to get LocationConstraint
            import re
            match = re.search(r'<LocationConstraint>([^<]+)</LocationConstraint>', response.text)
            if match:
                region = match.group(1)
                print(f"  ✓ Auto-detected region for bucket '{bucket_name}': {region} (via location query)")
                return region
            else:
                # Empty LocationConstraint means us-east-1
                if '<LocationConstraint/>' in response.text or '<LocationConstraint></LocationConstraint>' in response.text:
                    print(f"  ✓ Auto-detected region for bucket '{bucket_name}': us-east-1 (via location query)")
                    return 'us-east-1'
    except Exception as e:
        print(f"  ✗ Location query failed for '{bucket_name}': {e}")
    
    print(f"  ✗ Failed to detect region for bucket '{bucket_name}' using all methods")
    return None

def list_files_in_bucket(bucket_name, region):
    """
    List all files in a bucket and return structured data.
    Returns a dictionary with bucket info, files, and extension statistics.
    """
    result = {
        "bucket_name": bucket_name,
        "region": region,
        "scan_timestamp": datetime.now().isoformat(),
        "files": [],
        "extension_statistics": {},
        "errors": []
    }
    
    try:
        # Create a session without providing credentials
        session = boto3.Session()
        config = botocore.config.Config(signature_version=botocore.UNSIGNED)
        s3 = session.client('s3', region_name=region, config=config)

        # List objects in the bucket
        objects = s3.list_objects_v2(Bucket=bucket_name)

        extension_count = {}  # Dictionary to count file extensions

        for obj in objects.get('Contents', []):
            file_key = obj['Key']
            file_size_bytes = obj['Size']
            file_size_mb = file_size_bytes / (1024 * 1024)
            
            # URL encode the file key to handle spaces and special characters
            encoded_key = quote(file_key, safe='/')
            
            # Construct the appropriate URL based on bucket name
            if bucket_has_dots(bucket_name):
                # Path-style URL for buckets with dots
                if region != 'us-east-1':
                    link = f"https://s3.{region}.amazonaws.com/{bucket_name}/{encoded_key}"
                else:
                    link = f"https://s3.amazonaws.com/{bucket_name}/{encoded_key}"
            else:
                # Virtual-hosted style URL for buckets without dots
                link = f"https://{bucket_name}.s3.amazonaws.com/{encoded_key}"
            
            # Add file info to results - now includes bucket_name and region
            file_info = {
                "bucket_name": bucket_name,
                "region": region,
                "key": file_key,
                "url": link,
                "size_bytes": file_size_bytes,
                "size_mb": round(file_size_mb, 2),
                "last_modified": obj['LastModified'].isoformat()
            }
            result["files"].append(file_info)
            
            print(f"Bucket: {bucket_name}, Region: {region}, Link: {link}, File: {file_key}, Size: {file_size_mb:.2f} MB")
            
            # Count file extensions
            _, file_extension = os.path.splitext(file_key)
            if file_extension:
                extension_count[file_extension] = extension_count.get(file_extension, 0) + 1

        # Sort extensions by count (descending order)
        sorted_extensions = sorted(extension_count.items(), key=lambda x: x[1], reverse=True)
        result["extension_statistics"] = dict(sorted_extensions)
        
        # Print extension statistics
        for extension, count in sorted_extensions:
            print(f"Bucket: {bucket_name}, Extension: {extension}, Count: {count}")

    except botocore.exceptions.ClientError as e:
        error_msg = ""
        if e.response['Error']['Code'] == 'NoSuchBucket':
            error_msg = f"Bucket {bucket_name} not found in region {region}"
            print(error_msg)
        else:
            error_msg = f"An error occurred in region {region}: {str(e)}"
            print(error_msg)
        result["errors"].append(error_msg)
    
    return result

def is_valid_region(region_str):
    """
    Check if a string looks like a valid AWS region.
    Returns True if it matches the pattern of AWS regions.
    """
    if not region_str:
        return False
    
    # Common AWS region patterns: us-east-1, eu-west-2, ap-southeast-1, etc.
    # Must start with valid prefix AND contain a dash followed by direction and number
    valid_prefixes = ['us-', 'eu-', 'ap-', 'sa-', 'ca-', 'me-', 'af-', 'cn-']
    
    # Check if it starts with a valid prefix
    if not any(region_str.startswith(prefix) for prefix in valid_prefixes):
        return False
    
    # Check if it follows the pattern: prefix-direction-number (e.g., us-east-1, eu-west-2)
    # This helps distinguish from bucket names like "us-bucket" or "eu-data"
    parts = region_str.split('-')
    if len(parts) < 3:  # Need at least 3 parts: us-east-1
        return False
    
    # The last part should typically be a number for valid AWS regions
    try:
        int(parts[-1])
        return True
    except ValueError:
        return False

def parse_command_line_args():
    """
    Parse command-line arguments for bucket names, optional regions, and combine flag.
    Expected format: [--combine] bucket1 [region1] bucket2 [region2] ...
    Returns a tuple: (combine_flag, list of tuples [(bucket1, region1), ...])
    Region will be None if not provided (for auto-detection)
    
    This function intelligently handles mixed input:
    - bucket1 bucket2 bucket3 (all auto-detect)
    - bucket1 us-east-1 bucket2 us-west-2 (all explicit)
    - bucket1 bucket2 us-west-2 bucket3 (mixed: bucket1 auto, bucket2 explicit, bucket3 auto)
    """
    if len(sys.argv) < 2:
        return False, None  # No command-line arguments provided
    
    args = sys.argv[1:]
    combine = False
    
    # Check for --combine flag
    if args[0] == '--combine':
        combine = True
        args = args[1:]  # Remove the flag from args
    
    if len(args) == 0:
        return combine, None
    
    # Parse arguments - can be bucket names alone or bucket-region pairs
    buckets = []
    i = 0
    while i < len(args):
        bucket_name = args[i]
        region = None
        
        # Check if the next argument exists and is a region
        if i + 1 < len(args) and is_valid_region(args[i + 1]):
            region = args[i + 1]
            print(f"DEBUG: Parsed '{bucket_name}' with explicit region '{region}'")
            i += 2  # Skip both bucket and region
        else:
            print(f"DEBUG: Parsed '{bucket_name}' - region will be auto-detected")
            i += 1  # Skip just the bucket, region will be auto-detected
        
        buckets.append((bucket_name, region))
    
    return combine, buckets

if __name__ == '__main__':
    # Try to get buckets from command-line arguments
    combine_mode, cmd_buckets = parse_command_line_args()
    
    # Use command-line buckets if provided, otherwise use default list
    if cmd_buckets:
        buckets_to_process = cmd_buckets
        print(f"\nUsing {len(buckets_to_process)} bucket(s) from command-line arguments")
        print(f"Combine mode: {'ON' if combine_mode else 'OFF'}")
        print(f"Buckets to process: {buckets_to_process}\n")
    else:
        buckets_to_process = public_buckets
        print(f"\nUsing {len(buckets_to_process)} bucket(s) from default list")
        print(f"Combine mode: {'ON' if combine_mode else 'OFF'}\n")
    
    # Auto-detect regions where needed
    print("=" * 80)
    print("REGION DETECTION PHASE")
    print("=" * 80)
    processed_buckets = []
    for bucket, region in buckets_to_process:
        if region is None:
            print(f"\nAuto-detecting region for bucket: {bucket}")
            detected_region = get_bucket_region(bucket)
            if detected_region is None:
                print(f"⚠ WARNING: Skipping bucket '{bucket}' - could not detect region\n")
                continue
            processed_buckets.append((bucket, detected_region))
        else:
            print(f"\nUsing explicit region '{region}' for bucket: {bucket}")
            processed_buckets.append((bucket, region))
    
    print("\n" + "=" * 80)
    print(f"Successfully processed {len(processed_buckets)} out of {len(buckets_to_process)} buckets")
    print("=" * 80 + "\n")
    
    if not processed_buckets:
        print("ERROR: No valid buckets to process. Exiting.")
        sys.exit(1)
    
    if combine_mode:
        # COMBINE MODE: All buckets in one JSON file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'Combined_{timestamp}.json'
        
        combined_results = {
            "scan_timestamp": datetime.now().isoformat(),
            "total_buckets": len(processed_buckets),
            "buckets": [],
            "global_extension_statistics": {}
        }
        
        # Dictionary to accumulate extension counts across all buckets
        global_extension_count = {}
        
        # Scan all buckets and collect results
        for bucket, region in processed_buckets:
            print(f"\n{'=' * 80}")
            print(f"Scanning bucket: {bucket} in region: {region}")
            print("=" * 80)
            bucket_result = list_files_in_bucket(bucket, region)
            combined_results["buckets"].append(bucket_result)
            
            # Accumulate extension statistics for global count
            for extension, count in bucket_result["extension_statistics"].items():
                global_extension_count[extension] = global_extension_count.get(extension, 0) + count
            
            print(f"\n✓ Completed scanning {bucket}")
        
        # Sort global extension statistics by count (descending order)
        sorted_global_extensions = sorted(global_extension_count.items(), key=lambda x: x[1], reverse=True)
        combined_results["global_extension_statistics"] = dict(sorted_global_extensions)
        
        # Print global extension statistics
        print(f"\n{'=' * 80}")
        print("GLOBAL EXTENSION STATISTICS ACROSS ALL BUCKETS")
        print(f"{'=' * 80}")
        for extension, count in sorted_global_extensions:
            print(f"Extension: {extension}, Total Count: {count}")
        
        # Write combined results to single JSON file AFTER all buckets are scanned
        with open(output_file, 'w') as f:
            json.dump(combined_results, f, indent=2)
        
        print(f"\n{'=' * 80}")
        print(f"✓ All results saved to: {output_file}")
        print(f"✓ Total buckets scanned: {len(processed_buckets)}")
        print("=" * 80)
        
    else:
        # SEPARATE MODE: Individual JSON file per bucket
        for bucket, region in processed_buckets:
            print(f"\n{'=' * 80}")
            print(f"Scanning bucket: {bucket} in region: {region}")
            print("=" * 80)
            
            # Generate unique output filename for each bucket with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f'{bucket}_{timestamp}.json'
            
            # Scan the bucket
            bucket_result = list_files_in_bucket(bucket, region)
            
            # Write results to JSON file
            with open(output_file, 'w') as f:
                json.dump(bucket_result, f, indent=2)
            
            print(f"\n✓ Completed scanning {bucket}. Results saved to {output_file}")
