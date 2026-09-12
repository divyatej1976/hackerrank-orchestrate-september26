from typing import List
from engine.candidate_evaluator import CandidatePlan

class PlanRanker:
    @staticmethod
    def rank_candidates(candidates: List[CandidatePlan]) -> CandidatePlan:
        '''
        Ranks candidate plans according to the 6-tier preference rules:
        1. Complete by desired_completion_date (True before False)
        2. Require no spending changes (none before non-none)
        3. Minimize total amount paid
        4. Start payment earlier (first_date ascending)
        5. Use fewer payments (num_payments ascending)
        6. Lowest payment_option_id ascending
        '''
        if not candidates:
            raise ValueError('Candidate list cannot be empty')
            
        def sort_key(plan: CandidatePlan):
            # 1. Complete by deadline (0 if completes by deadline, 1 if not)
            c1 = 0 if plan.completes_by_deadline else 1
            # 2. No spending changes (0 if none, 1 if requires changes)
            c2 = 0 if plan.spending_changes == 'none' else 1
            # 3. Minimize total amount paid
            c3 = plan.total_amount
            # 4. Start payment earlier
            c4 = plan.first_date
            # 5. Use fewer payments
            c5 = plan.num_payments
            # 6. Lowest payment option ID
            c6 = plan.option_id
            
            return (c1, c2, c3, c4, c5, c6)
            
        ranked = sorted(candidates, key=sort_key)
        return ranked[0]
