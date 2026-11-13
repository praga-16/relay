import csv
import json
import threading
from pathlib import Path
import numpy as np

FIELDS = ['request_id', 'scenario', 'source', 'start_time', 'first_token_ms', 'total_ms',
          'status', 'retries', 'tokens_in', 'tokens_out', 'retrieval_setting', 'answer_grade']
SOURCES = {'real', 'stand-in'}
STATUSES = {'ok', 'rate_limited', 'timeout', 'error'}
GRADES = {'correct', 'wrong', 'refused_correctly', 'refused_wrongly'}


class Logger:
    def __init__(self, directory):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)
        self.csv = self.directory / 'results.csv'; self.raw = self.directory / 'diagnostics.jsonl'
        self.lock = threading.Lock()
        if not self.csv.exists():
            with self.csv.open('w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(FIELDS)

    def record(self, row, diagnostic):
        if set(row) != set(FIELDS):
            raise ValueError("results row schema mismatch")
        if row['source'] not in SOURCES or row['status'] not in STATUSES:
            raise ValueError("results row has an invalid source or status")
        if row['answer_grade'] not in GRADES and row['answer_grade'] is not None:
            raise ValueError("results row has an invalid answer grade")
        with self.lock:
            with self.csv.open('a', newline='', encoding='utf-8') as f:
                csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
            with self.raw.open('a', encoding='utf-8') as f:
                f.write(json.dumps(diagnostic, ensure_ascii=True) + '\n')


def percentiles(values):
    valid = [float(v) for v in values if v is not None and v != '']
    return dict(zip(('p50', 'p95', 'p99'), np.percentile(valid, [50, 95, 99], method='linear').tolist())) if valid else None
