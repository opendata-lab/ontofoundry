-- Fictional property-repair schema for the advanced concept-scope eval: structure only, no rows.
CREATE DATABASE IF NOT EXISTS eval_property DEFAULT CHARACTER SET utf8mb4;
USE eval_property;
CREATE TABLE IF NOT EXISTS buildings (building_no VARCHAR(8) PRIMARY KEY, floors INT NOT NULL) COMMENT='楼栋';
CREATE TABLE IF NOT EXISTS houses (house_no VARCHAR(16) PRIMARY KEY, building_no VARCHAR(8) NOT NULL, area DECIMAL(8,2)) COMMENT='房屋';
CREATE TABLE IF NOT EXISTS residents (resident_no VARCHAR(12) PRIMARY KEY, resident_name VARCHAR(40) NOT NULL, phone VARCHAR(20), house_no VARCHAR(16) NOT NULL) COMMENT='住户';
CREATE TABLE IF NOT EXISTS repair_orders (order_no VARCHAR(16) PRIMARY KEY, resident_no VARCHAR(12) NOT NULL, worker_no VARCHAR(8), reported_at DATETIME NOT NULL, description VARCHAR(200), urgency VARCHAR(8) NOT NULL COMMENT '紧急程度', score TINYINT COMMENT '住户评分', finished_at DATETIME) COMMENT='报修单（工单）';
CREATE TABLE IF NOT EXISTS workers (worker_no VARCHAR(8) PRIMARY KEY, worker_name VARCHAR(40) NOT NULL, trade VARCHAR(12) NOT NULL COMMENT '工种') COMMENT='维修工';
CREATE TABLE IF NOT EXISTS shifts (worker_no VARCHAR(8) NOT NULL, shift_date DATE NOT NULL, shift_type VARCHAR(8) NOT NULL COMMENT '班次', building_no VARCHAR(8) NOT NULL, PRIMARY KEY (worker_no, shift_date, shift_type)) COMMENT='排班';
CREATE TABLE IF NOT EXISTS worker_buildings (worker_no VARCHAR(8) NOT NULL, building_no VARCHAR(8) NOT NULL, PRIMARY KEY (worker_no, building_no)) COMMENT='维修工负责楼栋';
CREATE TABLE IF NOT EXISTS spare_parts (part_no VARCHAR(12) PRIMARY KEY, part_name VARCHAR(60) NOT NULL, unit_price DECIMAL(10,2) NOT NULL, stock INT NOT NULL) COMMENT='备件';
CREATE TABLE IF NOT EXISTS order_parts (order_no VARCHAR(16) NOT NULL, part_no VARCHAR(12) NOT NULL, PRIMARY KEY (order_no, part_no)) COMMENT='报修单使用的备件';
