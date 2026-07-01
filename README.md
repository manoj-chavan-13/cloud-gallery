# Cloud Gallery

A Python Flask web application for managing AWS S3 buckets. It provides an intuitive interface to create buckets and folders, upload files, rename items, and delete objects directly from your AWS S3 buckets.

## Prerequisites

- Python 3.8+
- AWS Account with S3 Access
- IAM User credentials with necessary S3 permissions

## How to Clone and Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/manoj-chavan-13/cloud-gallery.git
   cd cloud-gallery
   ```

2. **Create a virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Environment Variables:**
   Create a `.env` file in the root of the project with your AWS credentials:
   ```env
   SECRET_KEY=your_flask_secret_key_here
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your_aws_access_key_id
   AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
   ```

## How to Run

1. **Start the Flask server:**
   ```bash
   python app.py
   ```

2. **Access the application:**
   Open your web browser and navigate to **[http://127.0.0.1:3000](http://127.0.0.1:3000)**.

## Features

- View and list available S3 buckets
- Create new buckets with specified region support
- Navigate through nested directories/folders
- Upload files (up to 10MB per request)
- Create new folders within buckets
- Rename existing files
- Delete files and folders seamlessly
