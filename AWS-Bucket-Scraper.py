import boto3
import botocore
import os

# List of public S3 buckets along with their regions
public_buckets = [("mybucket1", "us-east-1"), ("mybucket2", "us-east-1")]

def list_files_in_bucket(bucket_name, region, output_file, extension_statistics):
    try:
        # Create a session without providing credentials
        session = boto3.Session()
        config = botocore.config.Config(signature_version=botocore.UNSIGNED)
        s3 = session.client('s3', region_name=region, config=config)

        # List objects in the bucket
        objects = s3.list_objects_v2(Bucket=bucket_name)

        extension_count = {}  # Dictionary to count file extensions

        with open(output_file, 'a') as file:  # Open the file in append mode
            for obj in objects.get('Contents', []):
                file_key = obj['Key']
                file_size_mb = obj['Size'] / (1024 * 1024)
                print(f"Bucket: {bucket_name}, Region: {region}, File: {file_key}, Size: {file_size_mb:.2f} MB\n")
                file.write(f"Bucket: {bucket_name}, Region: {region}, File: {file_key}, Size: {file_size_mb:.2f} MB\n")
                # Count file extensions
                _, file_extension = os.path.splitext(file_key)
                if file_extension:
                    extension_count[file_extension] = extension_count.get(file_extension, 0) + 1

        # Close the 'with' block for objects here

        # Update the extension statistics dictionary
        for extension, count in extension_count.items():
            extension_statistics[extension] = extension_statistics.get(extension, 0) + count

    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            with open(output_file, 'a') as file:
                print(f"Bucket: {bucket_name} not found in region {region}.\n")
                file.write(f"Bucket: {bucket_name} not found in region {region}.\n")
        else:
            with open(output_file, 'a') as file:
                print(f"Bucket: {bucket_name}, An error occurred in region {region}: {e}\n")
                file.write(f"Bucket: {bucket_name}, An error occurred in region {region}: {e}\n")

if __name__ == '__main__':
    output_file = 'AWS-Bucket-Scraper.txt'  # Specify the name of the output file
    with open(output_file, 'w') as file:  # Create or clear the output file
        file.write('')  # Clear the file

    extension_statistics = {}  # Dictionary to collect extension statistics

    for bucket, region in public_buckets:
        list_files_in_bucket(bucket, region, output_file, extension_statistics)

    # Print file extension statistics across all buckets
    with open(output_file, 'a') as file:  # Open the file in append mode
        file.write("\nFile Extension Statistics Across All Buckets:\n")
        for extension, count in extension_statistics.items():
            print(f"Extension: {extension}, Count: {count}\n")
            file
