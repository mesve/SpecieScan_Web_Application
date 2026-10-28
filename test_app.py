#!/usr/bin/env python3
"""
Quick test script for SpecieScan Web Application
Tests basic functionality without needing .mzML files
"""

import os
import io
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (
    app,
    processing_state,
    data_store,
    REFERENCE_DATABASES,
    get_builtin_reference_database,
    load_reference_dataframe,
    parse_marker_masses,
)
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
        assert 'step0' in state, "Step 0 state not in API response"
        print("   ✓ State API works")

        # Test optional Step 0 endpoints
        print("\n3. Testing optional Step 0...")
        response = client.get('/api/step0/download')
        assert response.status_code == 404, \
            f"Step 0 download should be 404 before conversion, got {response.status_code}"
        response = client.post(
            '/api/step0/upload',
            data={'file': (io.BytesIO(b'not a zip'), 'data.txt')},
            content_type='multipart/form-data'
        )
        assert response.status_code == 400, \
            f"Step 0 should reject non-ZIP uploads, got {response.status_code}"
        print("   ✓ Step 0 endpoints respond correctly")

        # Test step processing (Step 1)
        print("\n4. Testing step processing...")
        response = client.post('/api/step/1')
        assert response.status_code == 200, f"Step 1 returned {response.status_code}"
        result = json.loads(response.data)
        assert result['status'] == 'completed', f"Step 1 failed: {result}"
        print("   ✓ Step 1 processing works")

        # Test step 2 without files: must fail cleanly (no simulated data)
        print("\n5. Testing step 2 (should fail without files, no simulation)...")
        response = client.post('/api/step/2')
        assert response.status_code == 200, f"Step 2 returned {response.status_code}"
        result = json.loads(response.data)
        assert 'status' in result, "Step 2 result missing status"
        assert result['status'] == 'error', \
            f"Step 2 should error without uploaded files, got: {result['status']}"
        print(f"   ✓ Step 2 handled (status: {result['status']})")

        # Test all built-in reference databases load with marker columns
        print("\n6. Testing built-in reference databases...")
        for key, entry in REFERENCE_DATABASES.items():
            path, label = get_builtin_reference_database(key)
            reference_df = load_reference_dataframe(path)
            assert len(reference_df) > 0, f"{key}: no species rows"
            assert len(reference_df.columns) > 4, f"{key}: no marker columns"
            print(f"   ✓ {entry['label']}: {len(reference_df)} species, "
                  f"{len(reference_df.columns) - 4} markers")

        # Test multi-mass marker cells used by the Fish database
        assert parse_marker_masses('1600/ 1588') == [1600.0, 1588.0]
        assert parse_marker_masses('2450/2541') == [2450.0, 2541.0]
        assert parse_marker_masses('2754•') == [2754.0]
        assert parse_marker_masses('') == []
        print("   ✓ Multi-mass marker cells parsed correctly")

        # Test custom reference database upload through Step 9
        print("\n7. Testing custom reference database upload...")
        import numpy as np

        data_store['peaks_arrays'] = [(
            np.array([1105.6, 1180.6, 1196.6, 1427.7]),
            np.array([100.0, 90.0, 80.0, 70.0])
        )]
        processing_state['uploaded_files'] = [{'name': 'TEST_A1.mzML'}]

        custom_csv = (
            'Order,Family,Species,ZooMS_taxon,marker1,marker2\n'
            'Artiodactyla,Bovidae,Bos taurus,Bos,1105.6,1200/1300\n'
        )

        response = client.post(
            '/api/step/9',
            data={'reference_mode': 'default', 'reference_db_key': 'eurasia_mammals'},
        )
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['status'] == 'completed', f"Default DB failed: {result}"
        assert result['reference_source'] == 'specie_scan_2024'
        print("   ✓ Default database runs identification")

        response = client.post(
            '/api/step/9',
            data={
                'reference_mode': 'custom',
                'reference_db': (io.BytesIO(custom_csv.encode('utf-8')), 'my_reference.csv'),
            },
            content_type='multipart/form-data',
        )
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['status'] == 'completed', f"Custom DB failed: {result}"
        assert result['reference_source'] == 'custom'
        assert result['reference_database'] == 'my_reference.csv'
        print("   ✓ Custom database upload runs identification")

        response = client.post(
            '/api/step/9',
            data={
                'reference_mode': 'custom',
                'reference_db': (
                    io.BytesIO(b'Order,Family,Species,marker1\nA,B,C,1105.6\n'),
                    'broken.csv'
                ),
            },
            content_type='multipart/form-data',
        )
        result = json.loads(response.data)
        assert result['status'] == 'error', "Broken custom DB should be rejected"
        assert 'ZooMS_taxon' in result['message'], result['message']
        print("   ✓ Invalid custom database rejected with a clear message")

        # Clean up the fake peaks and any uploaded reference file.
        data_store['peaks_arrays'] = None
        processing_state['uploaded_files'] = []
        from app import _step9_cleanup
        _step9_cleanup()

    print("\n" + "=" * 50)
    print("All tests passed! ✓")
    print("\nThe application should now work correctly.")
    print("If you're still seeing errors in the browser, check:")
    print("  1. Browser console for JavaScript errors")
    print("  2. Flask server output for Python errors")
    print("  3. That you've refreshed the browser after code changes")


if __name__ == '__main__':
    test_app()
