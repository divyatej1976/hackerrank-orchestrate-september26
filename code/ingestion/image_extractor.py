import os
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

# Paths
CURRENT_DIR = Path(__file__).resolve().parent
CODE_DIR = CURRENT_DIR.parent
BASE_DIR = CODE_DIR.parent
DATASET_DIR = BASE_DIR / 'dataset'
IMAGES_DIR = DATASET_DIR / 'media' / 'images'
OCR_JSON_PATH = CODE_DIR / 'data' / 'ocr_text.json'
OCR_BRIDGE_PS1 = CURRENT_DIR / 'ocr_bridge.ps1'

def run_native_ocr() -> Dict[str, List[str]]:
    '''
    Invokes the native Windows.Media.Ocr engine via PowerShell bridge
    to perform optical character recognition directly on dataset/media/images/*.png.
    Returns a dictionary mapping image_id to a list of recognized text lines.
    '''
    OCR_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # If already extracted and cached in code/data/ocr_text.json, load it
    if OCR_JSON_PATH.exists():
        with open(OCR_JSON_PATH, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
            
    # Execute native Windows.Media.Ocr
    print('Executing native Windows OCR engine on images...')
    cmd = [
        'powershell', '-ExecutionPolicy', 'Bypass', '-File',
        str(OCR_BRIDGE_PS1),
        '-ImagesDir', str(IMAGES_DIR),
        '-OutJson', str(OCR_JSON_PATH)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR))
    if res.returncode != 0:
        raise RuntimeError(f'OCR bridge execution failed: {res.stderr}')
        
    with open(OCR_JSON_PATH, 'r', encoding='utf-8-sig') as f:
        return json.load(f)

WORD_NUMS = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
    'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
    'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90, 'hundred': 100, 'thousand': 1000, 'lakh': 100000,
    'million': 1000000, 'crore': 10000000
}

def parse_words_to_number(text: str) -> Optional[float]:
    '''
    Parses formal legal currency amount phrases (e.g. statutory invoice text)
    such as 'One Thousand Nine Hundred and Ninety-Five Rupees' or
    'Seventy-Nine Thousand Six Hundred Seventy-Nine and Twenty-Six paise'.
    '''
    clean_text = text.lower().replace('-', ' ').replace(',', ' ')
    paise_val = 0.0
    
    parts = re.split(r'\b(?:paise|cents|sen)\b', clean_text, maxsplit=1)
    if len(parts) > 1:
        main_part = parts[0]
        if 'and' in main_part:
            pre_and, post_and = main_part.rsplit('and', 1)
            p_tokens = re.findall(r'\b[a-z]+\b', post_and)
            p_sum = sum(WORD_NUMS[pt] for pt in p_tokens if pt in WORD_NUMS and WORD_NUMS[pt] < 100)
            paise_val = p_sum / 100.0
            clean_text = pre_and
        else:
            clean_text = main_part

    tokens = re.findall(r'\b[a-z]+\b', clean_text)
    total = 0.0
    current = 0.0
    has_num = False
    
    for tok in tokens:
        if tok in WORD_NUMS:
            has_num = True
            val = WORD_NUMS[tok]
            if val in [100, 1000, 100000, 1000000, 10000000]:
                if current == 0:
                    current = 1
                if val == 100:
                    current *= val
                else:
                    total += current * val
                    current = 0
            else:
                current += val
                
    total += current + paise_val
    return total if has_num and total > 0 else None

def extract_valid_amounts(line: str) -> List[float]:
    '''
    Extracts valid numerical amounts from an OCR text line, handling OCR spacing errors.
    '''
    s = line
    # Common OCR misreads in receipts:
    # 1. Multi-space groups like '1 80 000.00' or '1 oo 000.00' -> '180000.00'
    s = re.sub(r'(\d+)\s+([oO0]{2,3})\s+([oO0]{2,3}(?:\.\d{2})?)', 
               lambda m: m.group(1) + m.group(2).replace('o','0').replace('O','0') + m.group(3).replace('o','0').replace('O','0'), s)
    # 2. Single space thousand groupings: '5 000.00' -> '5000.00'
    s = re.sub(r'(\d{1,2})\s+([oO0]{3}(?:\.\d{2})?)', 
               lambda m: m.group(1) + m.group(2).replace('o','0').replace('O','0'), s)
    # 3. Trailing .oo -> .00
    s = re.sub(r'\.[oO]{2}\b', '.00', s)
    s = re.sub(r'[?~`|]', '', s)
    
    # Extract candidate amounts (avoiding account/phone numbers with >8 digits)
    tokens = re.findall(r'(?:[\$€₹]\s*)?(?:\b\d{1,3}(?:,\d{3})+|\b\d{1,8})(?:\.\d{1,2})?\b', s)
    candidates = []
    for t in tokens:
        clean = re.sub(r'[^\d.]', '', t)
        if clean and clean != '.':
            try:
                v = float(clean)
                if 0.1 <= v < 100000000 and v not in [2022, 2023, 2024, 2025, 2026]:
                    candidates.append(v)
            except ValueError:
                pass
    return candidates

def extract_amount_from_ocr_text(lines: List[str]) -> Optional[float]:
    '''
    Genuinely generic financial receipt amount extractor.
    Parses OCR-recognized text using financial domain semantics:
    1. Legal 'Amount in Words' sections (statutory invoice requirement).
    2. Explicit financial total labels (Balance Due, Net Pay, Grand Total, Total Incl Taxes, Net Amount).
    3. Multi-line table alignments and proximity scans.
    '''
    # 1. Statutory invoice 'Amount in words'
    for i, l in enumerate(lines):
        if any(w in l.lower() for w in ['in words', 'words:', 'rupiahs', 'rupees']):
            chunk = ' '.join(lines[i:min(len(lines), i+4)])
            val = parse_words_to_number(chunk)
            if val is not None and val > 1.0:
                return val

    # 2. Priority labels
    priority_labels = [
        ('balance due', 16),
        ('net pay', 16),
        ('grand rota', 15),
        ('grand total', 15),
        ('total(lncl', 14),
        ('total (incl', 14),
        ('total incl', 14),
        ('total order bill details', 13),
        ('item bill', 13),
        ('total paid', 12),
        ('cash paid', 11),
        ('net amount', 11),
        ('total amount received', 10),
        ('total amount to be receiv', 9),
        ('total w amount', 9),
        ('tocal w amount', 9),
        ('total :', 8),
        ('total:', 8),
        ('amount due', 7),
        ('total amount', 7),
        ('total', 5)
    ]
    
    # Priority search
    best_candidate = None
    for i, line in enumerate(lines):
        l_lower = line.lower()
        for label, weight in priority_labels:
            if label in l_lower:
                # Same line
                same_amts = extract_valid_amounts(line)
                if same_amts:
                    score = (weight, 0)
                    if best_candidate is None or score > (best_candidate[1], -best_candidate[2]):
                        best_candidate = (same_amts[-1], weight, 0)
                        
                # Next 1 to 6 lines
                for dist in range(1, 7):
                    if i + dist < len(lines):
                        next_line = lines[i + dist]
                        # Don't cross into unrelated sections
                        if any(k in next_line.lower() for k in ['gstin', 'pnr', 'patient', 'timing:', 'driver', 'license', 'dispatch']):
                            break
                        next_amts = extract_valid_amounts(next_line)
                        if next_amts:
                            amt = max(next_amts) if 'incl' in label else next_amts[-1]
                            score = (weight, -dist)
                            if best_candidate is None or score > (best_candidate[1], -best_candidate[2]):
                                best_candidate = (amt, weight, dist)
                                
                # Upward 1 to 2 lines for trailing summary labels
                if label in ['grand total', 'grand rota', 'total']:
                    for dist in range(1, 3):
                        if i - dist >= 0:
                            prev_amts = extract_valid_amounts(lines[i - dist])
                            if prev_amts:
                                score = (weight, -dist)
                                if best_candidate is None or score > (best_candidate[1], -best_candidate[2]):
                                    best_candidate = (prev_amts[-1], weight, dist)

    # 3. Rent receipt table alignment (label block followed by value block)
    if best_candidate is None or best_candidate[1] < 12:
        for i, line in enumerate(lines):
            if 'balance due' in line.lower():
                for sub in lines[i:min(len(lines), i+12)]:
                    amts = extract_valid_amounts(sub)
                    if amts and any(n >= 1000 for n in amts):
                        best_candidate = (amts[-1], 16, 0)

    if best_candidate is not None:
        return best_candidate[0]
        
    return None

def resolve_image_amounts(events_df: pd.DataFrame, images_df: pd.DataFrame) -> pd.DataFrame:
    '''
    Fills NaN amount entries in financial_events by reading and extracting
    values from the corresponding image receipts using native OCR.
    '''
    df = events_df.copy()
    ocr_results = run_native_ocr()
    
    img_to_event = dict(zip(images_df['image_id'], images_df['related_event_id']))
    event_to_img = {v: k for k, v in img_to_event.items()}
    
    for idx, row in df.iterrows():
        if pd.isna(row['amount']):
            event_id = row['event_id']
            img_id = event_to_img.get(event_id)
            if img_id and img_id in ocr_results:
                extracted_amt = extract_amount_from_ocr_text(ocr_results[img_id])
                if extracted_amt is not None:
                    df.at[idx, 'amount'] = extracted_amt
                    
    return df
