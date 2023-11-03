import boto3
import botocore

# List of public S3 buckets
public_buckets = ["MyBucket"]  # Replace with your bucket names

def list_files_in_bucket(bucket_name):
    try:
        # Create a session without providing credentials
        session = boto3.Session()
        config = botocore.config.Config(signature_version=botocore.UNSIGNED)
        s3 = session.client('s3', region_name='us-east-1', config=config)  # Specify your region

        # List objects in the bucket
        objects = s3.list_objects_v2(Bucket=bucket_name)

        for obj in objects.get('Contents', []):
            file_key = obj['Key']
            file_size_mb = obj['Size'] / (1024 * 1024)
            print(f"Bucket: {bucket_name}, File: {file_key}, Size: {file_size_mb:.2f} MB")

    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f"Bucket: {bucket_name} not found.")
        else:
            print(f"Bucket: {bucket_name}, An error occurred: {e}")

if __name__ == '__main__':
    for bucket in public_buckets:
        list_files_in_bucket(bucket)
