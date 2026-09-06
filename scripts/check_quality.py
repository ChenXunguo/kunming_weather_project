import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.prediction_model import TemperaturePredictor
from analyzer.correlation_analyzer import CorrelationAnalyzer
from logs.logger import setup_logger
import pandas as pd

logger = setup_logger("check_model")


def check_model_performance():
    """检查模型性能"""
    predictor = TemperaturePredictor()

    # 尝试加载最新模型（如果有保存的话）
    model_files = list(predictor.model_dir.glob("temp_predictor_*.pkl"))
    if model_files:
        # 加载最新的模型
        latest_model = sorted(model_files)[-1]
        logger.info(f"找到已保存模型: {latest_model}")
        # 加载逻辑 (此处略，可扩展)
    else:
        logger.info("未找到已保存模型，执行训练...")
        metrics = predictor.train_and_evaluate_pipeline(days=60, target_hours=6)
        if metrics:
            print("\n模型性能指标:")
            print(f"  测试集 RMSE: {metrics['test_rmse']:.3f} ℃")
            print(f"  测试集 MAE:  {metrics['test_mae']:.3f} ℃")
            print(f"  测试集 R²:   {metrics.get('r2', 0):.3f}")

            # 特征重要性：当前模型未导出该指标，如需要可在 prediction_model 中补充
            if 'feature_importance' in metrics:
                print("\nTop 5 重要特征:")
                for feat, imp in list(metrics['feature_importance'].items())[:5]:
                    print(f"  {feat}: {imp:.4f}")


def check_latest_correlation():
    """查看最新相关性"""
    analyzer = CorrelationAnalyzer()
    df = analyzer.load_recent_data(30)
    if not df.empty:
        corr_with_temp = analyzer.analyze_correlation_with_temp(df)
        print("\n与气温相关性最强的变量:")
        print(corr_with_temp.head(5))


if __name__ == "__main__":
    print("=" * 50)
    print("1. 模型性能检查")
    check_model_performance()
    print("\n" + "=" * 50)
    print("2. 最新相关性分析")
    check_latest_correlation()