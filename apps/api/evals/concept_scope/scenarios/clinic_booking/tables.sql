-- Fictional clinic schema for the concept-scope eval: structure only, no rows.
CREATE DATABASE IF NOT EXISTS eval_clinic DEFAULT CHARACTER SET utf8mb4;
USE eval_clinic;
CREATE TABLE IF NOT EXISTS departments (dept_id VARCHAR(8) PRIMARY KEY, dept_name VARCHAR(40) NOT NULL) COMMENT='科室';
CREATE TABLE IF NOT EXISTS doctors (doctor_id VARCHAR(8) PRIMARY KEY, doctor_name VARCHAR(40) NOT NULL, dept_id VARCHAR(8) NOT NULL, title VARCHAR(20) COMMENT '职称') COMMENT='医生';
CREATE TABLE IF NOT EXISTS patients (patient_id VARCHAR(12) PRIMARY KEY, patient_name VARCHAR(40) NOT NULL, gender VARCHAR(4), birth_date DATE) COMMENT='患者';
CREATE TABLE IF NOT EXISTS appointments (appt_no VARCHAR(16) PRIMARY KEY, patient_id VARCHAR(12) NOT NULL, doctor_id VARCHAR(8) NOT NULL, appt_date DATE NOT NULL, slot VARCHAR(16), status VARCHAR(8) NOT NULL COMMENT '预约状态') COMMENT='预约';
CREATE TABLE IF NOT EXISTS prescriptions (rx_no VARCHAR(16) PRIMARY KEY, appt_no VARCHAR(16) NOT NULL, issued_at DATETIME NOT NULL, total_amount DECIMAL(10,2) NOT NULL) COMMENT='处方';
CREATE TABLE IF NOT EXISTS prescription_items (rx_no VARCHAR(16) NOT NULL, line_no INT NOT NULL, drug_code VARCHAR(12) NOT NULL, quantity INT NOT NULL, PRIMARY KEY (rx_no, line_no)) COMMENT='处方明细';
CREATE TABLE IF NOT EXISTS drugs (drug_code VARCHAR(12) PRIMARY KEY, drug_name VARCHAR(60) NOT NULL, unit_price DECIMAL(10,2) NOT NULL, category VARCHAR(20)) COMMENT='药品';
CREATE TABLE IF NOT EXISTS daily_visit_stats (stat_date DATE NOT NULL, dept_id VARCHAR(8) NOT NULL, visit_count INT NOT NULL, PRIMARY KEY (stat_date, dept_id)) COMMENT='每日就诊人次统计（夜间汇总）';
