#!/usr/bin/env python3
"""
Flask Web UI for SOXUARTool
Provides a simple web interface for the User Access Processor tool
"""

import os
import logging
import tempfile
import uuid
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
from werkzeug.utils import secure_filename

# Import existing processors
from core.ad_client import ActiveDirectoryClient
from processors.great_plains import GreatPlainsProcessor
from processors.defi_los import DefiLOSProcessor
from processors.defi_servicing import DefiServicingProcessor
from processors.defi_xlos import DefiXLOSProcessor
from processors.datascan import DatascanProcessor
from utils.config import Config

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key-change-this')

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'downloads'
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB max file size

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Processor configurations
PROCESSORS = {
    'great_plains': {
        'name': 'Great Plains (ERP System)',
        'description': 'Display name lookup with name component fallback',
        'file_types': ['csv'],
        'class': GreatPlainsProcessor
    },
    'defi_los': {
        'name': 'Defi LOS (Loan Origination)',
        'description': 'User Name → email username fallback, role extraction',
        'file_types': ['csv'],
        'class': DefiLOSProcessor
    },
    'defi_servicing': {
        'name': 'Defi Servicing (Loan Servicing)',
        'description': 'SFSE prefix handling, status filtering',
        'file_types': ['csv'],
        'class': DefiServicingProcessor
    },
    'defi_xlos': {
        'name': 'Defi XLOS (Extended LOS)',
        'description': 'UserID → Email address fallback',
        'file_types': ['csv'],
        'class': DefiXLOSProcessor
    },
    'datascan': {
        'name': 'Datascan (Excel Access Reviews)',
        'description': 'Excel processing, permission matrix analysis',
        'file_types': ['xlsx', 'xls'],
        'class': DatascanProcessor
    }
}


def allowed_file(filename, processor_type):
    """Check if file extension is allowed for the processor"""
    if '.' not in filename:
        return False

    extension = filename.rsplit('.', 1)[1].lower()
    allowed_extensions = PROCESSORS.get(processor_type, {}).get('file_types', [])
    return extension in allowed_extensions


def setup_logging():
    """Setup logging for the web application"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = log_dir / f"webapp_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )


@app.route('/')
def index():
    """Main page with upload form"""
    return render_template('index.html', processors=PROCESSORS)


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and processing"""
    try:
        # Validate form data
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('index'))

        file = request.files['file']
        processor_type = request.form.get('processor')
        no_filters = request.form.get('no_filters') == 'on'
        role_extraction = request.form.get('role_extraction') == 'on'
        sheet_name = request.form.get('sheet_name', '').strip() or None

        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('index'))

        if not processor_type or processor_type not in PROCESSORS:
            flash('Invalid processor selected', 'error')
            return redirect(url_for('index'))

        if not allowed_file(file.filename, processor_type):
            allowed_types = ', '.join(PROCESSORS[processor_type]['file_types'])
            flash(f'Invalid file type. Allowed types for {PROCESSORS[processor_type]["name"]}: {allowed_types}',
                  'error')
            return redirect(url_for('index'))

        # Check file size
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning

        if file_size > MAX_FILE_SIZE:
            flash(f'File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB', 'error')
            return redirect(url_for('index'))

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Save uploaded file
        filename = secure_filename(file.filename)
        input_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{filename}")
        file.save(input_path)

        # Process the file
        result = process_file(job_id, input_path, processor_type, no_filters, role_extraction, sheet_name)

        if result['success']:
            return render_template('results.html',
                                   job_id=job_id,
                                   processor_name=PROCESSORS[processor_type]['name'],
                                   stats=result.get('stats'),
                                   output_files=result.get('output_files', []),
                                   logs=result.get('logs', []))
        else:
            flash(f'Processing failed: {result["error"]}', 'error')
            return redirect(url_for('index'))

    except Exception as e:
        app.logger.error(f"Upload error: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))


def process_file(job_id, input_path, processor_type, no_filters, role_extraction, sheet_name):
    """Process the uploaded file using the selected processor"""
    try:
        app.logger.info(f"Starting processing job {job_id} with processor {processor_type}")

        # Load configuration
        config = Config()
        if not config.validate_ad_config():
            missing_vars = config.get_missing_ad_vars()
            return {
                'success': False,
                'error': f'Missing AD configuration: {", ".join(missing_vars)}'
            }

        # Generate output file paths
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"{job_id}_{processor_type}_{timestamp}"

        output_files = []
        stats = {}

        with ActiveDirectoryClient(
                config.ad_server, config.ad_username,
                config.ad_password, config.base_dn
        ) as ad_client:

            if processor_type == 'datascan':
                # Handle Datascan (Excel) processor
                output_path = os.path.join(OUTPUT_FOLDER, f"{base_filename}_processed.xlsx")

                processor = DatascanProcessor(ad_client, input_path, sheet_name)
                raw_data = processor.load_data()
                processed_data = processor.process_permissions()
                processor.export_processed_data(output_path)

                output_files.append({
                    'filename': os.path.basename(output_path),
                    'path': output_path,
                    'description': 'Processed Excel file with multiple analysis sheets'
                })

                stats = {
                    'total_records': len(raw_data),
                    'processed_records': len(processed_data),
                    'success_rate': 100.0
                }

            else:
                # Handle CSV processors
                output_path = os.path.join(OUTPUT_FOLDER, f"{base_filename}_processed.csv")
                role_output_path = None

                if role_extraction and processor_type in ['great_plains', 'defi_los']:
                    role_output_path = os.path.join(OUTPUT_FOLDER, f"{base_filename}_roles.csv")

                # Get processor class and instantiate
                processor_class = PROCESSORS[processor_type]['class']
                processor = processor_class(ad_client)

                # Process the file
                processing_stats = processor.process_users(
                    input_path,
                    output_path,
                    apply_filters=not no_filters,
                    role_output_csv=role_output_path
                )

                # Add main output file
                output_files.append({
                    'filename': os.path.basename(output_path),
                    'path': output_path,
                    'description': 'Main processed output with AD data'
                })

                # Add role output file if created
                if role_output_path and os.path.exists(role_output_path):
                    output_files.append({
                        'filename': os.path.basename(role_output_path),
                        'path': role_output_path,
                        'description': 'Role analysis output'
                    })

                # Convert stats for display
                stats = {
                    'total_records': processing_stats.total_records,
                    'successful_lookups': processing_stats.successful_lookups,
                    'failed_lookups': processing_stats.failed_lookups,
                    'success_rate': processing_stats.success_rate
                }

        app.logger.info(f"Processing job {job_id} completed successfully")
        return {
            'success': True,
            'output_files': output_files,
            'stats': stats
        }

    except Exception as e:
        app.logger.error(f"Processing job {job_id} failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        # Clean up input file
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
        except:
            pass


@app.route('/download/<filename>')
def download_file(filename):
    """Download processed file"""
    try:
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        if not os.path.exists(file_path):
            flash('File not found', 'error')
            return redirect(url_for('index'))

        return send_file(file_path, as_attachment=True)

    except Exception as e:
        app.logger.error(f"Download error: {str(e)}")
        flash('Error downloading file', 'error')
        return redirect(url_for('index'))


@app.route('/health')
def health_check():
    """Health check endpoint"""
    config = Config()
    ad_config_valid = config.validate_ad_config()

    return jsonify({
        'status': 'healthy' if ad_config_valid else 'configuration_error',
        'ad_config_valid': ad_config_valid,
        'processors_available': list(PROCESSORS.keys())
    })


if __name__ == '__main__':
    setup_logging()

    # Check configuration on startup
    config = Config()
    if not config.validate_ad_config():
        missing_vars = config.get_missing_ad_vars()
        app.logger.warning(f"Missing AD configuration: {', '.join(missing_vars)}")
        print("⚠️  Warning: Missing AD configuration variables. The application will start but processing will fail.")
        print(f"   Missing: {', '.join(missing_vars)}")
    else:
        app.logger.info("AD configuration validated successfully")

    # Start the application
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    print(f"🚀 Starting SOXUARTool Web UI on port {port}")
    print(f"📁 Upload folder: {UPLOAD_FOLDER}")
    print(f"📁 Download folder: {OUTPUT_FOLDER}")
    print(f"🔧 Debug mode: {debug}")

    app.run(host='0.0.0.0', port=port, debug=debug)