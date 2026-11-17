"""Run the 'Check MATLAB link' logic outside Pro:  propy tests\\run_check.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noisebox import pipeline  # noqa: E402

print("OK" if pipeline.check_link(pipeline.PrintLog()) else "PROBLEM")
