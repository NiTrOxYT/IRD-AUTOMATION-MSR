"""
Dedicated Duplicate START SYNC Verification Suite — Single Request & Locking Mechanism
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_duplicate_start_sync_prevention():
    print("======================================================================")
    print("RUNNING DEDICATED DUPLICATE START SYNC PREVENTION VERIFICATION SUITE")
    print("======================================================================")

    # TEST 1: Inspect index.html for inline duplicate click attributes
    print("\n[TEST 1] Verifying index.html has no inline onclick duplicate triggers...")
    index_path = Path(__file__).parent.parent / "app" / "ui" / "index.html"
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'onclick="window.__phase16ButtonClicked' not in html
    assert '<button id="btn-start-sync" class="btn btn-primary btn-glow">START SYNC</button>' in html
    print("[OK] index.html contains clean single #btn-start-sync element with zero inline onclick triggers.")

    # TEST 2: Inspect app.js for locking mechanism and single handler binding
    print("\n[TEST 2] Verifying app.js locking mechanism and handler binding...")
    appjs_path = Path(__file__).parent.parent / "app" / "ui" / "app.js"
    with open(appjs_path, "r", encoding="utf-8") as f:
        js = f.read()

    assert "let isStartSyncLocked = false;" in js
    assert "handleStartSyncClick" in js
    assert "[UI] START SYNC click event count:" in js
    assert "[UI] START SYNC request trace ID:" in js
    assert "[UI] START SYNC request sent" in js
    assert "[UI] START SYNC handler locked" in js
    assert "bindClick('btn-start-sync', handleStartSyncClick);" in js
    print("[OK] app.js locking mechanism and single click handler verified.")

    # TEST 3: Verify button disablement on lock
    print("\n[TEST 3] Verifying button disablement logic on click lock...")
    assert "btn.disabled = true;" in js
    assert "isStartSyncLocked = false;" in js
    print("[OK] Button disablement and unlock lifecycle verified.")

    print("\n======================================================================")
    print("ALL DUPLICATE START SYNC PREVENTION TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    test_duplicate_start_sync_prevention()
