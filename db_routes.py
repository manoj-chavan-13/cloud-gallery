import os
import boto3
import json
from botocore.exceptions import ClientError
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

db_bp = Blueprint('db', __name__, url_prefix='/db')

def get_dynamodb_client():
    S3_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    
    if not AWS_ACCESS_KEY or not AWS_SECRET_KEY:
        raise Exception("AWS Credentials are not fully set in .env")
        
    return boto3.client(
        'dynamodb',
        region_name=S3_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

@db_bp.route('/')
def list_tables():
    try:
        dynamodb = get_dynamodb_client()
        response = dynamodb.list_tables()
        tables = response.get('TableNames', [])
        return render_template('database.html', tables=tables, current_table=None)
    except Exception as e:
        return render_template('database.html', tables=[], current_table=None, error=str(e))

@db_bp.route('/table/<table_name>')
def view_table(table_name):
    try:
        dynamodb = get_dynamodb_client()
        
        # Get table schema and status
        table_desc = dynamodb.describe_table(TableName=table_name)
        key_schema = table_desc['Table']['KeySchema']
        table_status = table_desc['Table']['TableStatus']
        
        tables_response = dynamodb.list_tables()
        tables = tables_response.get('TableNames', [])
        
        # If table is creating, don't scan
        if table_status != 'ACTIVE':
            return render_template('database.html', 
                                   tables=tables,
                                   current_table=table_name, 
                                   items=[], 
                                   headers=[],
                                   key_schema=key_schema,
                                   table_status=table_status)
        
        response = dynamodb.scan(TableName=table_name)
        items = response.get('Items', [])
        
        simplified_items = []
        for item in items:
            simplified_item = {}
            for k, v in item.items():
                val = list(v.values())[0] if v else ''
                simplified_item[k] = val
            simplified_items.append(simplified_item)
            
        headers = set()
        for item in simplified_items:
            headers.update(item.keys())
        headers = list(headers)
        
        return render_template('database.html', 
                               tables=tables,
                               current_table=table_name, 
                               items=simplified_items, 
                               headers=headers,
                               key_schema=key_schema,
                               table_status=table_status)
    except Exception as e:
        flash(f'Error viewing table {table_name}: {str(e)}', 'error')
        return redirect(url_for('db.list_tables'))


# --- API ROUTES FOR REAL-TIME OPERATIONS ---

@db_bp.route('/api/create_table', methods=['POST'])
def api_create_table():
    try:
        data = request.json
        table_name = data.get('table_name')
        partition_key = data.get('partition_key')
        
        if not table_name or not partition_key:
            return jsonify({'success': False, 'message': 'Table Name and Partition Key are required'}), 400
            
        dynamodb = get_dynamodb_client()
        dynamodb.create_table(
            TableName=table_name,
            KeySchema=[{'AttributeName': partition_key, 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': partition_key, 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        return jsonify({'success': True, 'message': f'Table "{table_name}" creation initiated.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@db_bp.route('/api/table/<table_name>/status', methods=['GET'])
def api_table_status(table_name):
    try:
        dynamodb = get_dynamodb_client()
        table_desc = dynamodb.describe_table(TableName=table_name)
        return jsonify({'success': True, 'status': table_desc['Table']['TableStatus']})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@db_bp.route('/api/table/<table_name>/insert', methods=['POST'])
def api_insert_item(table_name):
    try:
        data = request.json
        item_data = data.get('item_json')
        
        if not item_data:
            return jsonify({'success': False, 'message': 'Item JSON data is required'}), 400
             
        try:
            if isinstance(item_data, str):
                parsed_data = json.loads(item_data)
            else:
                parsed_data = item_data
        except json.JSONDecodeError:
            return jsonify({'success': False, 'message': 'Invalid JSON format provided.'}), 400
            
        dynamodb = get_dynamodb_client()
        dynamo_item = {}
        for k, v in parsed_data.items():
            if isinstance(v, str):
                dynamo_item[k] = {'S': v}
            elif isinstance(v, bool):
                dynamo_item[k] = {'BOOL': v}
            elif isinstance(v, (int, float)):
                dynamo_item[k] = {'N': str(v)}
            else:
                dynamo_item[k] = {'S': json.dumps(v)}
                
        dynamodb.put_item(TableName=table_name, Item=dynamo_item)
        return jsonify({'success': True, 'message': 'Data inserted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@db_bp.route('/api/table/<table_name>/delete', methods=['POST'])
def api_delete_item(table_name):
    try:
        data = request.json
        key_data = data.get('key_json')
        
        if isinstance(key_data, str):
            parsed_key = json.loads(key_data)
        else:
            parsed_key = key_data
            
        dynamodb = get_dynamodb_client()
        
        # Get actual table schema to know the key types
        table_desc = dynamodb.describe_table(TableName=table_name)
        key_schema = {k['AttributeName']: k['KeyType'] for k in table_desc['Table']['KeySchema']}
        attr_defs = {a['AttributeName']: a['AttributeType'] for a in table_desc['Table']['AttributeDefinitions']}
        
        dynamo_key = {}
        for k_name in key_schema.keys():
            if k_name in parsed_key:
                val = parsed_key[k_name]
                attr_type = attr_defs.get(k_name, 'S')
                dynamo_key[k_name] = {attr_type: str(val)}
            else:
                return jsonify({'success': False, 'message': f'Missing primary key component: {k_name}'}), 400
            
        dynamodb.delete_item(TableName=table_name, Key=dynamo_key)
        return jsonify({'success': True, 'message': 'Record deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
