import re
import pandas as pd
from typing import Dict, Any, List, Set, Optional

class MessageParser:
    '''
    Generalized multilingual (EN/ID) message parser extracting domain financial amendments:
    - salary overrides and effective dates
    - employment termination / contract end
    - rent adjustments (percentages)
    - unconfirmed / disputed credits and pending refunds to ignore
    '''
    def __init__(self, messages_df: pd.DataFrame):
        self.messages_df = messages_df
        self.user_messages: Dict[str, List[Dict[str, Any]]] = {}
        for _, row in messages_df.iterrows():
            uid = str(row['user_id']).strip()
            if uid not in self.user_messages:
                self.user_messages[uid] = []
            self.user_messages[uid].append(row.to_dict())
            
    def get_user_adjustments(self, user_id: str) -> Dict[str, Any]:
        adjustments = {
            'salary_override': None,
            'salary_effective_date': None,
            'salary_ended': False,
            'rent_increase_pct': 0.0,
            'ignore_events': set()
        }
        
        msgs = self.user_messages.get(user_id, [])
        for m in msgs:
            txt = str(m.get('message_text', '')).strip()
            rel_ev = str(m.get('related_event_id', '')).strip() if pd.notna(m.get('related_event_id')) else None
            
            # 1. Termination / contract end
            # Differentiate partial termination (one household stream ended, remaining continues) from total termination
            is_partial_term = bool(re.search(r'\b(?:one household employment record has ended|salah satu sumber pendapatan.*telah berakhir)\b', txt, re.IGNORECASE))
            if is_partial_term:
                # Do NOT end all salary; continuing stream remains active
                adjustments['salary_ended'] = False
            else:
                term_pattern = r'\b(?:contract (?:has )?ended|seasonal contract has ended|no off-season income|employment has ended|resignation|kontrak (?:telah )?berakhir|pemutusan hubungan)\b'
                if re.search(term_pattern, txt, re.IGNORECASE):
                    adjustments['salary_ended'] = True
                
            # 2. Unconfirmed / disputed credits to ignore
            unconf_pattern = r'\b(?:refund has been initiated but has not reached|reversal has not been posted|payout is still pending|isn\'t withdrawable|not withdrawable|belum disetujui|belum masuk|belum tercatat|tidak masuk pembayaran|no cash proceeds|market value has increased substantially|tidak ada hasil tunai)\b'
            if re.search(unconf_pattern, txt, re.IGNORECASE):
                if rel_ev:
                    adjustments['ignore_events'].add(rel_ev)
                    
            # 3. Rent increase
            rent_m = re.search(r'(?:increase[s]? monthly rent by|menaikkan biaya sewa(?: bulanan)? sebesar)\s+(\d+)%', txt, re.IGNORECASE)
            if rent_m:
                adjustments['rent_increase_pct'] = float(rent_m.group(1)) / 100.0
                
            rent_date_m = re.search(r'(?:rent.*effective from|applies from|berlaku mulai)\s+(\d{4}-\d{2}-\d{2})', txt, re.IGNORECASE)
            if rent_date_m:
                adjustments['rent_effective_date'] = rent_date_m.group(1)
                
            # 4. Salary updates
            sal_m = re.search(r'(?:salary (?:is|of|resumes)|pay is|first salary will be|reduced to|increased to|remaining confirmed monthly salary is|sisa gaji bulanan yang dikonfirmasi adalah|naik menjadi|dikurangi menjadi|gaji (?:pokok )?(?:yang dikonfirmasi )?adalah)\s+(?:[A-Z]{3}\s+)?([\d,]+(?:\.\d+)?)', txt, re.IGNORECASE)
            if sal_m:
                val_str = sal_m.group(1).replace(',', '')
                try:
                    adjustments['salary_override'] = float(val_str)
                except ValueError:
                    pass
                    
            date_m = re.search(r'(?:effective from|resumes on|expected on|credit date is|berlaku mulai|pada tanggal)\s+(\d{4}-\d{2}-\d{2})', txt, re.IGNORECASE)
            if date_m:
                adjustments['salary_effective_date'] = date_m.group(1)
                
        return adjustments
