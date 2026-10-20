#!/usr/bin/env python3
"""
Quick test script for SpecieScan Web Application
Tests basic functionality without needing .mzML files
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, processing_state
import json


def test_app():
    print("Testing SpecieScan Web Application...")
    print("=" * 50)

    # Test 1: Check initial state
    print("\n1. Testing initial state...")
    assert 'processing_data' in processing_state, "processing_data not in state"
    assert 'uploaded_files' in processing_state, "uploaded_files not in state"
    assert isinstance(processing_state['processing_data'], dict), "processing_data is not a dict"
    print("   ✓ Initial state is correct")

    # Test 2: Test Flask client
    print("\n2. Testing Flask endpoints...")
    with app.test_client() as client:
        # Test index page
        response = client.get('/')
        assert response.status_code == 200, f"Index returned {response.status_code}"
        print("   ✓ Index page loads (200)")

        # Test state endpoint
        response = client.get('/api/state')
        assert response.status_code == 200, f"State API returned {response.status_code}"
        state = json.loads(response.data)
        assert 'processing_data' in state, "processing_data not in API response"
        print("   ✓ State API works")

        # Test step processing (Step 1)
        print("\n3. Testing step processing...")
        response = client.post('/api/step/1')
        assert response.status_code == 200, f"Step 1 returned {response.status_code}"
        result = json.loads(response.data)
        assert result['status'] == 'completed', f"Step 1 failed: {result}"
        print("   ✓ Step 1 processing works")

        # Test step 2 without files: must fail cleanly (no simulated data)
        print("\n4. Testing step 2 (should fail without files, no simulation)...")
        response = client.post('/api/step/2')
        assert response.status_code == 200, f"Step 2 returned {response.status_code}"
        result = json.loads(response.data)
        assert 'status' in result, "Step 2 result missing status"
        assert result['status'] == 'error', \
            f"Step 2 should error without uploaded files, got: {result['status']}"
        print(f"   ✓ Step 2 handled (status: {result['status']})")

    print("\n" + "=" * 50)
    print("All tests passed! ✓")
    print("\nThe application should now work correctly.")
    print("If you're still seeing errors in the browser, check:")
    print("  1. Browser console for JavaScript errors")
    print("  2. Flask server output for Python errors")
    print("  3. That you've refreshed the browser after code changes")


if __name__ == '__main__':
    test_app()
