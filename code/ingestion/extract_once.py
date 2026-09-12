import os
import sys
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR / 'code'))
from ingestion.image_extractor import resolve_image_amounts

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = BASE_DIR / 'dataset'
IMAGES_CSV = DATASET_DIR / 'images.csv'
EVENTS_CSV = DATASET_DIR / 'financial_events.csv'
OUTPUT_ENRICHED_CSV = BASE_DIR / 'code' / 'data' / 'enriched_events.csv'

def extract_and_enrich():
    os.makedirs(OUTPUT_ENRICHED_CSV.parent, exist_ok=True)
    print(f'Reading raw events from {EVENTS_CSV}...')
    df_events = pd.read_csv(EVENTS_CSV)
    df_images = pd.read_csv(IMAGES_CSV)
    
    missing_count = df_events['amount'].isna().sum()
    print(f'Found {missing_count} events with missing amount in raw dataset.')
    
    # Enrich missing amounts dynamically via OCR extraction
    df_enriched = resolve_image_amounts(df_events, df_images)
    
    remaining_missing = df_enriched['amount'].isna().sum()
    print(f'Enriched {missing_count - remaining_missing} missing amounts using OCR image extraction.')
    if remaining_missing > 0:
        print(f'Warning: {remaining_missing} amounts could not be resolved.')
        
    df_enriched.to_csv(OUTPUT_ENRICHED_CSV, index=False)
    print(f'Saved enriched dataset to {OUTPUT_ENRICHED_CSV}')
    return OUTPUT_ENRICHED_CSV

if __name__ == '__main__':
    extract_and_enrich()
