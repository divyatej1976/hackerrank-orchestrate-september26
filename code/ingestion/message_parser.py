import re
import pandas as pd
from typing import Dict, Any, Optional

class MessageParser:
    def __init__(self, messages_df: pd.DataFrame):
        self.messages_df = messages_df
        self.user_messages: Dict[str, list] = {}
        for _, row in messages_df.iterrows():
            uid = str(row['user_id'])
            if uid not in self.user_messages:
                self.user_messages[uid] = []
            self.user_messages[uid].append(row)
            
    def get_user_adjustments(self, user_id: str) -> Dict[str, Any]:
        '''
        Parses messages for a user and returns financial adjustments:
        - salary_override: float or None
        - salary_effective_date: str or None
        - rent_increase_pct: float (e.g. 0.12 for 12%)
        - ignored_events: set of event_ids that should be ignored
        '''
        adjustments = {
            'salary_override': None,
            'salary_effective_date': None,
            'rent_increase_pct': 0.0,
            'ignore_events': set()
        }
        
        msgs = self.user_messages.get(user_id, [])
        for m in msgs:
            txt = str(m['message_text'])
            rel_ev = str(m['related_event_id']) if pd.notna(m['related_event_id']) else None
            
            # Rent increase (12%)
            if 'increases monthly rent by 12%' in txt or 'menaikkan biaya sewa bulanan sebesar 12%' in txt:
                adjustments['rent_increase_pct'] = 0.12
                
            # Salary updates
            # Patterns like: 'Gaji bulanan Anda naik menjadi IDR 42750000. Perubahan ini berlaku mulai 2025-08-15'
            # Or: 'Your temporary monthly pay is EUR 1037.52'
            # Or: 'Your confirmed salary is now expected on 2024-09-23'
            # Or: 'Your next salary is reduced to EUR 1422.85'
            # Or: 'Your first salary will be EUR 1661. The confirmed credit date is 2026-01-15'
            amt_match = re.search(r'(?:naik menjadi|reduced to|pay is|salary is|salary will be|dikonfirmasi adalah)\s+(?:[A-Z]{3}\s+)?([\d,]+(?:\.\d+)?)', txt, re.IGNORECASE)
            if amt_match:
                amt_str = amt_match.group(1).replace(',', '')
                try:
                    adjustments['salary_override'] = float(amt_str)
                except ValueError:
                    pass
                    
            date_match = re.search(r'(?:berlaku mulai|expected on|credit date is)\s+(\d{4}-\d{2}-\d{2})', txt, re.IGNORECASE)
            if date_match:
                adjustments['salary_effective_date'] = date_match.group(1)
                
            # Unsettled refunds, disputed charges
            if 'refund has been initiated but has not reached' in txt or 'Pengembalian dana sudah diproses, tetapi belum masuk' in txt:
                if rel_ev:
                    adjustments['ignore_events'].add(rel_ev)
            if 'reversal has not been posted' in txt or 'pembalikannya belum tercatat' in txt:
                if rel_ev:
                    adjustments['ignore_events'].add(rel_ev)
                    
        return adjustments
