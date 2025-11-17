#!/usr/bin/env python3
"""
Example test script for use with gpu_node_runner.sh
This can be used as a template for your own GPU testing scripts.
"""
import sys
import socket

def main():
    print('='*60)
    print('EXAMPLE GPU TEST SCRIPT')
    print('='*60)
    print('Python executable:', sys.executable)
    print('Hostname:', socket.gethostname())
    print()

    # Test 1: PyTorch CUDA check
    print('[TEST 1] PyTorch import and CUDA check')
    try:
        import torch
        print('  ✓ torch version:', torch.__version__)
        print('  ✓ CUDA available:', torch.cuda.is_available())
        if torch.cuda.is_available():
            print('  ✓ CUDA version:', torch.version.cuda)
            print('  ✓ GPU:', torch.cuda.get_device_name(0))
            print('  ✓ GPU memory:', f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")
    except Exception as e:
        print('  ✗ FAILED:', repr(e))
        return 1

    print()
    print('='*60)
    print('ALL TESTS PASSED ✓')
    print('='*60)
    return 0

if __name__ == '__main__':
    sys.exit(main())
