import pandas as pd
from typing import Dict

# Extracted amounts from the 16 media images mapped by image_id
IMAGE_AMOUNTS: Dict[str, float] = {
    'image_01': 4365000.0,   # Pay Slip Net Pay (IDR)
    'image_02': 100000.0,    # Rent Receipt Balance Due (INR)
    'image_03': 41272.0,     # Bill of Supply Net Amount (INR)
    'image_04': 2854.0,      # Grocery delivery Item Bill (INR)
    'image_05': 704.05,      # Telecom Bill Total Due (INR)
    'image_06': 1995.0,      # Quick Commerce Total (INR)
    'image_07': 8528.10,     # Restaurant Tax Invoice Total (INR)
    'image_08': 15339.0,     # Maintenance Receipt Total Received (INR)
    'image_09': 723.0,       # Water Bill Receipt Total Received (INR)
    'image_10': 79679.26,    # Invoice Balance Due (INR)
    'image_11': 3650.0,      # Provisional Hospital Bill Balance (INR)
    'image_12': 33.50,       # CityCab Taxi Total (USD)
    'image_13': 2298.0,      # Order Summary Total Paid (INR)
    'image_14': 4543.0,      # Pharmacy Bill Total (INR)
    'image_15': 9968.0,      # Flight Invoice Grand Total (INR)
    'image_16': 393.22,      # EV Charging Invoice Total (INR)
}

def resolve_image_amounts(events_df: pd.DataFrame, images_df: pd.DataFrame) -> pd.DataFrame:
    '''
    Fills NaN amount entries in financial_events using the extracted image values.
    '''
    df = events_df.copy()
    img_to_event = dict(zip(images_df['image_id'], images_df['related_event_id']))
    event_to_img = {v: k for k, v in img_to_event.items()}
    
    for idx, row in df.iterrows():
        if pd.isna(row['amount']):
            event_id = row['event_id']
            img_id = event_to_img.get(event_id)
            if img_id and img_id in IMAGE_AMOUNTS:
                df.at[idx, 'amount'] = IMAGE_AMOUNTS[img_id]
                
    return df
