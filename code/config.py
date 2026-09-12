import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / 'dataset'
MEDIA_DIR = DATASET_DIR / 'media' / 'images'

REQUESTS_FILE = DATASET_DIR / 'requests.csv'
SAMPLE_REQUESTS_FILE = DATASET_DIR / 'sample_requests.csv'
PROFILES_FILE = DATASET_DIR / 'financial_profiles.csv'
EVENTS_FILE = DATASET_DIR / 'financial_events.csv'
OPTIONS_FILE = DATASET_DIR / 'request_payment_options.csv'
EXCHANGE_RATES_FILE = DATASET_DIR / 'exchange_rates.csv'
MESSAGES_FILE = DATASET_DIR / 'messages.csv'
IMAGES_FILE = DATASET_DIR / 'images.csv'

OUTPUT_FILE = BASE_DIR / 'output.csv'
USAGE_REPORT_FILE = BASE_DIR / 'code' / 'evaluation' / 'usage_report.md'
CODE_ZIP_FILE = BASE_DIR / 'code.zip'

FORECAST_DAYS = 90
MAX_SPENDING_CHANGES = 3

REQUIRED_OUTPUT_COLUMNS = [
    'request_id',
    'amount_safe_to_pay',
    'affordability_status',
    'recommended_payment_method',
    'payment_plan',
    'earliest_date_for_full_payment',
    'spending_changes_needed',
    'decision_explanation'
]
