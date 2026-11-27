import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Application configuration class"""
    
    # Flask configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database configuration
    db_port = int(os.getenv('DB_PORT', 3306))
    use_ssl = os.getenv('DB_SSL', '').lower() in ('true', '1', 'yes') or db_port == 4000

    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': db_port,
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'delta_plus_erp'),
        'autocommit': False,
        'raise_on_warnings': True
    }

    if use_ssl:
        DB_CONFIG['ssl_disabled'] = False
        ssl_ca = os.getenv('DB_SSL_CA')
        if ssl_ca and os.path.exists(ssl_ca):
            DB_CONFIG['ssl_ca'] = ssl_ca
            DB_CONFIG['ssl_verify_cert'] = True
        else:
            # TiDB Cloud Serverless standard TLS
            ssl_verify = os.getenv('DB_SSL_VERIFY', 'true').lower() in ('true', '1', 'yes')
            DB_CONFIG['ssl_verify_cert'] = ssl_verify
    
    # Network configuration
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    
    # Upload configuration
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() in ('true', '1', 'yes')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Debug configuration
    DEBUG = os.getenv('FLASK_DEBUG', '0') == '1'
