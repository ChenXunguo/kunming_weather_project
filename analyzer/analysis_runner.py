import sys
from pathlib import Path
# 项目根路径加入搜索路径，必须在业务import之前执行
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime

from analyzer.correlation_analyzer import CorrelationAnalyzer
from analyzer.prediction_model import TemperaturePredictor

logger = logging.getLogger(__name__)


class AnalysisRunner:
    """统一分析调度器"""

    def __init__(self):
        self.corr_analyzer = CorrelationAnalyzer()
        self.predictor = TemperaturePredictor()

    def run_daily_analysis(self):
        """
        每日分析任务：
        1. 更新相关性分析（最近30天）
        2. 模型训练
        3. 生成当日预测
        :return: dict 各环节执行状态
        """
        logger.info("========== 开始每日分析任务 ==========")
        success_corr = False
        success_train = False
        success_predict = False

        # 1.相关性分析
        try:
            logger.info("执行相关性分析...")
            self.corr_analyzer.run_full_analysis(days=30)
            success_corr = True
        except Exception as e:
            logger.error(f"相关性分析失败: {e}", exc_info=True)

        # 2.模型训练
        try:
            logger.info("执行模型训练...")
            metrics = self.predictor.train_and_evaluate_pipeline(days=60, target_hours=6)
            if metrics:
                success_train = True
                logger.info(f"模型训练完成，测试集RMSE: {metrics['test_rmse']:.3f}℃")
            else:
                logger.warning("模型未训练成功，跳过预测步骤")
        except Exception as e:
            logger.error(f"模型训练失败: {e}", exc_info=True)

        # 3.生成未来预测：只有训练成功才执行预测
        if success_train:
            try:
                logger.info("生成短期预测...")
                pred_df = self.predictor.predict_future(6)
                if not pred_df.empty:
                    self.predictor.save_prediction_to_db(pred_df)
                    success_predict = True
                    logger.info(f"预测结果已保存: {pred_df.iloc[0]['prediction_time']} {pred_df.iloc[0]['predicted_temp']:.2f}℃")
            except Exception as e:
                logger.error(f"预测生成失败: {e}", exc_info=True)

        logger.info("========== 每日分析任务完成 ==========")
        return {
            "correlation_ok": success_corr,
            "train_ok": success_train,
            "predict_ok": success_predict,
            "run_time": datetime.now().isoformat()
        }



if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    runner = AnalysisRunner()
    result = runner.run_daily_analysis()
    logger.info(f"分析任务执行结果：{result}")
