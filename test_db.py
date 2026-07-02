import os
import boto3
from dotenv import load_dotenv

load_dotenv()

dynamodb = boto3.client('dynamodb', 
    region_name=os.environ.get('AWS_REGION'), 
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), 
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'))

table_name = os.environ.get('DYNAMODB_TABLE_NAME')

demo_item = {
    'cloud-gallery': {'S': 'demo_image_123.jpg'},
    'bucket': {'S': 'my-bucket-name'},
    'size_kb': {'N': '1024'},
    'uploaded_by': {'S': 'test_user'}
}

try:
    dynamodb.put_item(TableName=table_name, Item=demo_item)
    print("Demo data inserted successfully!")
except Exception as e:
    print("Error:", e)
