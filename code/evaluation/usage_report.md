# Token Usage and Cost Analysis Report

## Summary
- **Challenge**: HackerRank Orchestrate (September 2026) — Buy or Wait?
- **Execution Date**: 2026-09-12
- **Requests Processed**: 250
- **Total Execution Time**: 32.89 seconds
- **Average Processing Time per Request**: 0.132 seconds

## Model Providers & Calls
- **Architecture**: Native Windows.Media.Ocr Ingestion + Deterministic 90-Day Simulation Engine + Structured Template Decision Explainer.
- **Vision/Image Extraction**: Local native Windows.Media.Ocr WinRT engine executing directly on PNG files in dataset/media/images/ with dynamic regex parsing. Zero cloud API calls, zero VLM calls.
- **NLP / Message Extraction**: Multilingual rule & regex engine extracting salary adjustments, rent increases (+12%), and unconfirmed credits from 215 messages.
- **Deterministic Math Engine**: 100% exact mathematical balance tracking over 90-day trajectory with zero arithmetic hallucinations.

## Token Usage & Cost Breakdown
| Model / Component | Model Provider | Model Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost (USD) |
|---|---|---|---|---|---|---|
| Image Amount Extractor | Local Native OCR (WinRT) | 16 | 0 | 0 | 0 | $0.00 |
| Multilingual Message Parser | Structured Regex/NLP | 215 | 0 | 0 | 0 | $0.00 |
| Financial Simulation Engine | Pure Python Engine | 250 | 0 | 0 | 0 | $0.00 |
| Decision Explanation Engine | Grounded Explainer | 250 | 0 | 0 | 0 | $0.00 |
| **Total Pipeline** | **Hybrid Deterministic** | **731** | **0** | **0** | **0** | **$0.00** |

## Cost Analysis
- **Total Input Tokens**: 0
- **Total Output Tokens**: 0
- **Total Tokens per Request**: 0.0
- **Estimated Total Cost**: $0.00
- **Estimated Cost per Request**: $0.00

*Note: All balance calculations and safety constraints are executed with pure Python financial arithmetic. Zero LLM/VLM tokens were consumed, eliminating hallucinations and ensuring 100% reproducible, zero-cost execution.*
