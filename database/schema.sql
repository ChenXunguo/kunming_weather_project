-- ============================================================
-- 昆明气象数据智能分析系统 数据库建表脚本
-- 版本：v2.3（无外键 + 保留默认值，完全兼容现有 Python 代码）
-- 字符集：utf8mb4
-- 适用 MySQL：5.6 / 5.7 / 8.0
-- ============================================================

CREATE DATABASE IF NOT EXISTS `kunming_weather`
DEFAULT CHARACTER SET utf8mb4
DEFAULT COLLATE utf8mb4_unicode_ci;

USE `kunming_weather`;

-- -----------------------------------------------------------
-- 1. 站点信息表
-- -----------------------------------------------------------
DROP TABLE IF EXISTS `station_info`;
CREATE TABLE `station_info` (
  `station_id` INT NOT NULL AUTO_INCREMENT COMMENT '站点ID',
  `station_name` VARCHAR(128) DEFAULT NULL COMMENT '站点名称',
  `city` VARCHAR(64) NOT NULL COMMENT '所属城市',
  `latitude` DECIMAL(10,6) DEFAULT NULL COMMENT '纬度',
  `longitude` DECIMAL(10,6) DEFAULT NULL COMMENT '经度',
  `elevation` FLOAT DEFAULT NULL COMMENT '海拔高度(米)',
  `create_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`station_id`),
  UNIQUE KEY `uk_city_lat_lon` (`city`, `latitude`, `longitude`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='气象站点信息表';

-- -----------------------------------------------------------
-- 2. 气象数据表（核心表，无外键）
-- -----------------------------------------------------------
DROP TABLE IF EXISTS `weather_data`;
CREATE TABLE `weather_data` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `station_id` INT NOT NULL COMMENT '站点ID',
  `record_time` DATETIME NOT NULL COMMENT '记录时间(北京时间)',
  `collect_time` DATETIME DEFAULT NULL COMMENT '采集入库时间',
  `temp_current` DECIMAL(5,2) DEFAULT NULL COMMENT '当前气温(℃)',
  `temp_max` DECIMAL(5,2) DEFAULT NULL COMMENT '最高气温(℃)',
  `temp_min` DECIMAL(5,2) DEFAULT NULL COMMENT '最低气温(℃)',
  `feels_like` DECIMAL(5,2) DEFAULT NULL COMMENT '体感温度(℃)',
  `humidity` TINYINT UNSIGNED DEFAULT NULL COMMENT '相对湿度(%)',
  `pressure` SMALLINT UNSIGNED DEFAULT NULL COMMENT '大气压强(hPa)',
  `wind_speed` DECIMAL(5,2) DEFAULT NULL COMMENT '风速(m/s)',
  `wind_direction` SMALLINT UNSIGNED DEFAULT NULL COMMENT '风向角度(°)',
  `wind_gusts` DECIMAL(5,2) DEFAULT NULL COMMENT '阵风风速(m/s)',
  `cloud_cover` TINYINT UNSIGNED DEFAULT NULL COMMENT '云量(%)',
  `precipitation` DECIMAL(6,2) DEFAULT NULL COMMENT '降水量(mm/3h)【注：仅OpenWeatherMap预报接口提供，实况或其它来源可能为空】',
  `weather_desc` VARCHAR(100) DEFAULT NULL COMMENT '天气状况描述',
  `data_source` VARCHAR(50) DEFAULT NULL COMMENT '数据来源',
  `raw_data` TEXT DEFAULT NULL COMMENT '原始API报文',
  `data_type` TINYINT NOT NULL DEFAULT 1 COMMENT '数据类型：1=实况 2=预报',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_station_record_type` (`station_id`, `record_time`, `data_type`),
  KEY `idx_data_type` (`data_type`),
  KEY `idx_record_time` (`record_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='气象实况与预报数据表';

-- -----------------------------------------------------------
-- 3. 数据质量日志表
-- -----------------------------------------------------------
DROP TABLE IF EXISTS `data_quality_log`;
CREATE TABLE `data_quality_log` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `record_date` DATE NOT NULL COMMENT '统计日期',
  `total_records` INT DEFAULT NULL COMMENT '当日总记录数',
  `valid_records` INT DEFAULT NULL COMMENT '有效记录数',
  `outlier_count` INT DEFAULT NULL COMMENT '异常值修正数量',
  `null_filled_count` INT DEFAULT NULL COMMENT '缺失值填补数量',
  `validity_rate` DECIMAL(5,2) DEFAULT NULL COMMENT '数据有效率(%)，保留两位小数',
  `cleaning_details` TEXT DEFAULT NULL COMMENT '清洗详情备注',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_record_date` (`record_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日数据质量日志表';

-- -----------------------------------------------------------
-- 4. 分析结果表（保留 DEFAULT 1，无外键）
-- -----------------------------------------------------------
DROP TABLE IF EXISTS `analysis_results`;
CREATE TABLE `analysis_results` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `station_id` INT NOT NULL DEFAULT 1 COMMENT '站点ID（默认1，兼容旧代码）',
  `analysis_type` VARCHAR(30) NOT NULL COMMENT '分析类型：correlation/prediction/model_metric',
  `analysis_date` DATETIME NOT NULL COMMENT '分析基准时间',
  `variable_x` VARCHAR(50) DEFAULT NULL COMMENT '变量X(相关性分析用)',
  `variable_y` VARCHAR(50) DEFAULT NULL COMMENT '变量Y(相关性分析用)',
  `correlation_coefficient` DECIMAL(6,4) DEFAULT NULL COMMENT '皮尔逊相关系数',
  `prediction_value` DECIMAL(5,2) DEFAULT NULL COMMENT '预测值(气温等)',
  `model_params` JSON DEFAULT NULL COMMENT '模型参数/评估指标（JSON格式）',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_type_date` (`analysis_type`, `analysis_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='气象分析结果表';