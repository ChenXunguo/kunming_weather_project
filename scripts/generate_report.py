import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from visualizer.pdf_reporter import PDFReporter
from visualizer.dashboard_builder import DashboardBuilder
from logs.logger import setup_logger
import argparse

logger = setup_logger("report_script")


def main():
    parser = argparse.ArgumentParser(description="生成气象报告")
    parser.add_argument('--type', choices=['dashboard', 'quarterly', 'both'],
                        default='both', help='报告类型')
    parser.add_argument('--quarter', type=int, choices=[1, 2, 3, 4],
                        help='季度 (1‑4)')
    parser.add_argument('--year', type=int, help='年份')
    args = parser.parse_args()

    if args.type in ['dashboard', 'both']:
        logger.info("生成看板...")
        builder = DashboardBuilder()
        path = builder.build_dashboard(days=30)
        print(f"看板已生成: {path}")

    if args.type in ['quarterly', 'both']:
        logger.info("生成季度报告...")
        reporter = PDFReporter()
        path = reporter.generate_quarterly_report(quarter=args.quarter, year=args.year)
        print(f"季度报告已生成: {path}")


if __name__ == "__main__":
    main()
