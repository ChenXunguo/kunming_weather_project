import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from analyzer.analysis_runner import AnalysisRunner

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    runner = AnalysisRunner()
    res = runner.run_daily_analysis()
    print(res)
