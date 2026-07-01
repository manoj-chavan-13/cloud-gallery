import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB limit per request

# AWS S3 Configuration
S3_REGION = os.environ.get('AWS_REGION', 'us-east-1')
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')

s3_client = boto3.client(
    's3',
    region_name=S3_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    config=Config(signature_version='s3v4', s3={'addressing_style': 'path'})
)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    bucket_name = request.args.get('bucket', '')
    prefix = request.args.get('prefix', '')
    
    # If no bucket is selected, show list of buckets
    if not bucket_name:
        try:
            response = s3_client.list_buckets()
            buckets = response.get('Buckets', [])
            return render_template('index.html', 
                                   buckets=buckets, 
                                   current_bucket='', 
                                   current_prefix='',
                                   folders=[], files=[])
        except ClientError as e:
            flash(f'Error connecting to AWS: {str(e)}', 'error')
            return render_template('index.html', buckets=[], current_bucket='', current_prefix='')

    # If a bucket is selected, show its contents
    if prefix and not prefix.endswith('/'):
        prefix += '/'

    try:
        # 1. Dynamically get the REAL region of this specific bucket
        location_resp = s3_client.get_bucket_location(Bucket=bucket_name)
        bucket_region = location_resp.get('LocationConstraint')
        if bucket_region is None:
            bucket_region = 'us-east-1' # Default for older standard regions
            
        # 2. Create a specific client for this region to guarantee valid signatures
        region_client = boto3.client(
            's3',
            region_name=bucket_region,
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            config=Config(signature_version='s3v4', s3={'addressing_style': 'path'})
        )
        
        response = region_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
        
        folders = []
        if 'CommonPrefixes' in response:
            for p in response['CommonPrefixes']:
                folder_name = p['Prefix'][len(prefix):].strip('/')
                if folder_name:
                    folders.append({
                        'name': folder_name,
                        'full_prefix': p['Prefix']
                    })
                    
        files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'] == prefix:
                    continue
                
                file_name = obj['Key'][len(prefix):]
                try:
                    url = region_client.generate_presigned_url('get_object',
                                                            Params={'Bucket': bucket_name,
                                                                    'Key': obj['Key']},
                                                            ExpiresIn=3600)
                except ClientError:
                    url = None
                    
                files.append({
                    'name': file_name,
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'url': url
                })
                
        parent_prefix = ''
        if prefix:
            parts = prefix.strip('/').split('/')
            if len(parts) > 1:
                parent_prefix = '/'.join(parts[:-1]) + '/'
                
        return render_template('index.html', 
                               buckets=[],
                               folders=folders, 
                               files=files, 
                               current_bucket=bucket_name,
                               current_prefix=prefix,
                               parent_prefix=parent_prefix)
                               
    except ClientError as e:
        flash(f'Error accessing bucket: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/create_bucket', methods=['POST'])
def create_bucket():
    bucket_name = request.form.get('bucket_name')
    if not bucket_name:
        flash('Bucket name is required', 'error')
        return redirect(url_for('index'))
        
    try:
        if S3_REGION == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': S3_REGION}
            )
        flash(f'Bucket "{bucket_name}" created successfully!', 'success')
    except ClientError as e:
        flash(f'Failed to create bucket: {str(e)}', 'error')
        
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    bucket = request.form.get('bucket')
    if not bucket:
        flash('No bucket selected.', 'error')
        return redirect(url_for('index'))
        
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('index', bucket=bucket))
        
    files = request.files.getlist('file')
    prefix = request.form.get('prefix', '')
    
    if not files or files[0].filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('index', bucket=bucket, prefix=prefix))
        
    upload_count = 0
    error_count = 0
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            key = prefix + filename
            
            try:
                s3_client.upload_fileobj(
                    file,
                    bucket,
                    key,
                    ExtraArgs={'ContentType': file.content_type}
                )
                upload_count += 1
            except ClientError:
                error_count += 1
        else:
            error_count += 1
            
    if upload_count > 0:
        flash(f'Successfully uploaded {upload_count} file(s)', 'success')
    if error_count > 0:
        flash(f'Failed to upload {error_count} file(s) or invalid file type', 'error')
        
    return redirect(url_for('index', bucket=bucket, prefix=prefix))

@app.route('/create_folder', methods=['POST'])
def create_folder():
    bucket = request.form.get('bucket')
    folder_name = request.form.get('folder_name')
    prefix = request.form.get('prefix', '')
    
    if not bucket or not folder_name:
        flash('Bucket and Folder name are required', 'error')
        return redirect(url_for('index', bucket=bucket, prefix=prefix))
        
    folder_name = secure_filename(folder_name)
    key = prefix + folder_name + '/'
    
    try:
        s3_client.put_object(Bucket=bucket, Key=key)
        flash(f'Folder "{folder_name}" created', 'success')
    except ClientError as e:
        flash(f'Failed to create folder: {str(e)}', 'error')
        
    return redirect(url_for('index', bucket=bucket, prefix=prefix))

@app.route('/delete', methods=['POST'])
def delete_object():
    bucket = request.form.get('bucket')
    key = request.form.get('key')
    prefix = request.form.get('prefix', '')
    
    if not bucket or not key:
        flash('Bucket and Key are required for deletion', 'error')
        return redirect(url_for('index', bucket=bucket, prefix=prefix))
        
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
        flash('Item deleted successfully', 'success')
    except ClientError as e:
        flash(f'Failed to delete: {str(e)}', 'error')
        
    return redirect(url_for('index', bucket=bucket, prefix=prefix))

@app.route('/rename', methods=['POST'])
def rename_object():
    bucket = request.form.get('bucket')
    old_key = request.form.get('old_key')
    new_name = request.form.get('new_name')
    prefix = request.form.get('prefix', '')
    
    if not bucket or not old_key or not new_name:
        flash('Missing required fields for rename', 'error')
        return redirect(url_for('index', bucket=bucket, prefix=prefix))
        
    new_key = prefix + secure_filename(new_name)
    
    if '.' not in new_name and '.' in old_key:
        new_key += old_key[old_key.rfind('.'):]
        
    try:
        s3_client.copy_object(
            Bucket=bucket,
            CopySource={'Bucket': bucket, 'Key': old_key},
            Key=new_key
        )
        s3_client.delete_object(Bucket=bucket, Key=old_key)
        flash('File renamed successfully', 'success')
    except ClientError as e:
        flash(f'Failed to rename: {str(e)}', 'error')
        
    return redirect(url_for('index', bucket=bucket, prefix=prefix))

@app.route('/database')
def view_database():
    table_name = os.environ.get('DYNAMODB_TABLE_NAME')
    if not table_name:
        return render_template('database.html', configured=False)
        
    try:
        dynamodb = boto3.client(
            'dynamodb',
            region_name=S3_REGION,
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY
        )
        response = dynamodb.scan(TableName=table_name)
        items = response.get('Items', [])
        
        # Simplify dynamodb items for easy rendering
        simplified_items = []
        for item in items:
            simplified_item = {}
            for k, v in item.items():
                val = list(v.values())[0] if v else ''
                simplified_item[k] = val
            simplified_items.append(simplified_item)
            
        # Collect all unique headers
        headers = set()
        for item in simplified_items:
            headers.update(item.keys())
        headers = list(headers)
        
        return render_template('database.html', 
                               configured=True, 
                               table_name=table_name, 
                               items=simplified_items, 
                               headers=headers)
    except Exception as e:
        flash(f'Error accessing DynamoDB: {str(e)}', 'error')
        return render_template('database.html', configured=True, table_name=table_name, items=[], headers=[])

@app.errorhandler(413)
def request_entity_too_large(error):
    flash('File size exceeds the 10MB limit.', 'error')
    return redirect(request.referrer or url_for('index'))

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    flash(f'An unexpected system error occurred: {str(e)}', 'error')
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=3000)
