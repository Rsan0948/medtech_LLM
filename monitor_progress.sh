#!/bin/bash
# Progress monitor that logs every 100 entries

LOG_FILE="/tmp/teacher_progress.log"
LAST_COUNT=0

echo "=== Teacher Progress Monitor Started ===" > $LOG_FILE
echo "Started at: $(date)" >> $LOG_FILE
echo "" >> $LOG_FILE

while true; do
    # Count current responses
    if [ -f "data/app/teacher_responses.jsonl" ]; then
        COUNT=$(wc -l < data/app/teacher_responses.jsonl)
        
        # Log every 100 entries
        if [ $((COUNT / 100)) -gt $((LAST_COUNT / 100)) ] && [ $COUNT -ge 100 ]; then
            echo "=== Milestone: $COUNT responses ===" >> $LOG_FILE
            echo "Time: $(date)" >> $LOG_FILE
            
            # Calculate accuracy
            python3 << 'PYEOF' >> $LOG_FILE 2>&1
import json

try:
    with open('data/app/teacher_responses.jsonl', 'r') as f:
        records = [json.loads(l) for l in f if l.strip()]
    
    matches = sum(1 for r in records 
                  if r['verified_outcome'].lower() in r['teacher_classification'].lower()
                  or r['teacher_classification'].lower() in r['verified_outcome'].lower())
    
    print(f"Total: {len(records)}")
    print(f"Accuracy: {100*matches/len(records):.1f}% ({matches}/{len(records)})")
    
    # Breakdown by type
    from collections import Counter
    confusion = Counter((r['verified_outcome'], r['teacher_classification']) for r in records)
    print("\nTop classifications:")
    for (v, t), count in confusion.most_common(5):
        mark = "✓" if v.lower() in t.lower() or t.lower() in v.lower() else "✗"
        print(f"  {mark} {v} → {t}: {count}")
except Exception as e:
    print(f"Error: {e}")
PYEOF
            
            echo "" >> $LOG_FILE
            echo "Progress: $COUNT/1000 = $((COUNT/10))%" >> $LOG_FILE
            
            # Estimate completion
            if [ $COUNT -gt 0 ]; then
                # Rough estimate: 4 min per variant, 5 concurrent
                REMAINING=$((1000 - COUNT))
                ETA_MIN=$((REMAINING * 4 / 5))
                ETA_HOUR=$((ETA_MIN / 60))
                ETA_MIN_REM=$((ETA_MIN % 60))
                echo "ETA: ~${ETA_HOUR}h ${ETA_MIN_REM}m remaining" >> $LOG_FILE
            fi
            
            echo "" >> $LOG_FILE
            echo "========================================" >> $LOG_FILE
            echo "" >> $LOG_FILE
            
            # Also show notification
            echo "🎯 MILESTONE: $COUNT responses reached!"
            echo "   Check progress: tail -20 /tmp/teacher_progress.log"
        fi
        
        LAST_COUNT=$COUNT
    fi
    
    # Check every 30 seconds
    sleep 30
done
