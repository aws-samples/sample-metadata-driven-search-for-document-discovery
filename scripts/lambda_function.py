import json
import boto3
import os
import logging
# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    print("EVENT:", event)
    # Extract necessary information from the event
    bucket_name = event['bucketName']
    input_file_key = event['inputFiles'][0]['contentBatches'][0]['key']
    original_file_location = event['inputFiles'][0].get('originalFileLocation', {})
    # Initialize S3 client
    s3 = boto3.client('s3')
    processed_batches = []
    output_files = []
    # Read the JSON file from S3
    logger.info("bucket_name: %s", bucket_name)
    logger.info("input_file_key: %s", input_file_key)
    response = s3.get_object(Bucket=bucket_name, Key=input_file_key)
    file_content = response['Body'].read().decode('utf-8')
    # Parse the JSON content
    data = json.loads(file_content)
    # Set company
    company = None
    # Process each contentBody
    for item in data['fileContents']:
        content_body = item['contentBody']
        # Remove metadata tags and extract JSON
        metadata_start = content_body.find('<metadata>')
        metadata_end = content_body.find('</metadata>')
        if metadata_start != -1 and metadata_end != -1:
            metadata_json = content_body[metadata_start + 10:metadata_end].strip()
            content_body = content_body[:metadata_start].strip()
            # Set company
            metadata_as_json = json.loads(metadata_json)
            if company is None and 'company' in metadata_as_json:
                company = metadata_as_json["company"]
            else:
                metadata_as_json["company"] = company
            logger.info("metadata_json: %s", metadata_json)
            logger.info("content_body: %s", content_body)
            # Parse the metadata JSON and assign to contentMetadata
            item['contentMetadata'] = metadata_as_json
            item['contentBody'] = content_body
    filtered_objects = [obj for obj in data['fileContents'] if obj.get("contentBody")]
    new_data = {
        "fileContents": filtered_objects
    }

    # # Serialize the dictionary to JSON
    processed_json = json.dumps(new_data).encode('utf-8')
    # # Convert to bytes
    processed_json = bytes(processed_json)
    # Generate new output file name
    file_name, file_extension = os.path.splitext(input_file_key)
    output_file_key = f"{file_name}_output{file_extension}"
    # Save the processed JSON back to S3
    output_key = f"Output/{input_file_key}"
    s3.put_object(Bucket=bucket_name, Key=output_key, Body=processed_json)

    # Add processed batch information
    processed_batches.append({
        'key': output_key
    })
    # Prepare output file information
    output_file = {
        'originalFileLocation': original_file_location,
        'contentBatches': processed_batches
    }
    output_files.append(output_file)
    result = {'outputFiles': output_files}
    print("KB_CUSTOM_RESULT", result)
    return result