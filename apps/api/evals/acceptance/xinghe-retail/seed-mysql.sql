CREATE DATABASE xinghe_retail CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE xinghe_retail;
CREATE TABLE `members` (`member_id` VARCHAR(16) NOT NULL COMMENT '会员编号',`member_name` VARCHAR(64) NOT NULL COMMENT '会员姓名',`member_level` VARCHAR(8) NOT NULL COMMENT '会员等级：普通/银卡/金卡',`city` VARCHAR(32) NULL COMMENT '常住城市',`joined_on` DATE NOT NULL COMMENT '入会日期',`home_store_id` VARCHAR(16) NULL COMMENT '开卡门店',PRIMARY KEY (`member_id`)) COMMENT='会员';
CREATE TABLE `order_items` (`order_no` VARCHAR(20) NOT NULL COMMENT '订单号',`line_no` INTEGER NOT NULL COMMENT '行号',`sku` VARCHAR(16) NOT NULL COMMENT '商品编码',`qty` INTEGER NOT NULL COMMENT '数量',`unit_price` DECIMAL(10, 2) NOT NULL COMMENT '成交单价',PRIMARY KEY (`order_no`,`line_no`)) COMMENT='订单明细';
CREATE TABLE `orders` (`order_no` VARCHAR(20) NOT NULL COMMENT '订单号',`member_id` VARCHAR(16) NULL COMMENT '下单会员，散客为空',`store_id` VARCHAR(16) NOT NULL COMMENT '成交门店',`order_date` DATE NOT NULL COMMENT '下单日期',`status` VARCHAR(8) NOT NULL COMMENT '订单状态：已完成/已取消/待支付',`pay_amount` DECIMAL(12, 2) NOT NULL COMMENT '实付金额',PRIMARY KEY (`order_no`)) COMMENT='订单';
CREATE TABLE `products` (`sku` VARCHAR(16) NOT NULL COMMENT '商品编码',`product_name` VARCHAR(64) NOT NULL COMMENT '商品名称',`category` VARCHAR(32) NOT NULL COMMENT '品类',`list_price` DECIMAL(10, 2) NOT NULL COMMENT '标价',PRIMARY KEY (`sku`)) COMMENT='商品';
CREATE TABLE `stores` (`store_id` VARCHAR(16) NOT NULL COMMENT '门店编号',`store_name` VARCHAR(64) NOT NULL COMMENT '门店名称',`city` VARCHAR(32) NOT NULL COMMENT '所在城市',`opened_on` DATE NOT NULL COMMENT '开业日期',PRIMARY KEY (`store_id`)) COMMENT='门店';
CREATE TABLE `refunds` (`refund_no` VARCHAR(20) NOT NULL COMMENT '退款单号',`order_no` VARCHAR(20) NOT NULL COMMENT '原订单号',`refund_date` DATE NOT NULL COMMENT '退款日期',`refund_amount` DECIMAL(12,2) NOT NULL COMMENT '退款金额',`reason` VARCHAR(64) NULL COMMENT '退款原因',PRIMARY KEY (`refund_no`)) COMMENT='退款（显式补充物理结构）';
INSERT INTO xinghe_retail.orders VALUES
 ('O2026010001','M001','S01','2026-01-03','已完成',89.70),
 ('O2026010002','M002','S01','2026-01-05','已完成',33.60),
 ('O2026010003',NULL,'S02','2026-01-09','已完成',13.50),
 ('O2026010004','M003','S02','2026-01-15','已取消',44.00),
 ('O2026010005','M004','S03','2026-01-21','已完成',120.40),
 ('O2026020001','M001','S01','2026-02-02','已完成',58.40),
 ('O2026020002','M005','S03','2026-02-11','已完成',29.70),
 ('O2026020003','M006','S02','2026-02-14','已完成',76.60),
 ('O2026020004','M002','S01','2026-02-20','待支付',24.00),
 ('O2026020005',NULL,'S03','2026-02-26','已完成',9.90),
 ('O2026030001','M004','S03','2026-03-04','已完成',95.70),
 ('O2026030002','M001','S02','2026-03-09','已完成',44.00),
 ('O2026030003','M003','S02','2026-03-17','已完成',36.00),
 ('O2026030004','M006','S01','2026-03-22','已取消',19.90),
 ('O2026030005','M005','S03','2026-03-28','已完成',61.40);
INSERT INTO xinghe_retail.refunds VALUES
 ('R2026010001','O2026010005','2026-01-25',39.80,'生鲜破损'),
 ('R2026020001','O2026020003','2026-02-16',12.00,'口味不符'),
 ('R2026030001','O2026030001','2026-03-06',19.90,'生鲜破损');

INSERT INTO stores VALUES ('S01','星河晨光店','青岚','2020-01-01'),('S02','星河松溪店','澄川','2021-05-01'),('S03','星河云桥店','青岚','2022-03-01');
INSERT INTO members VALUES ('M001','林晓','金卡','青岚','2023-01-01','S01'),('M002','陈雨','银卡','青岚','2023-02-01','S01'),('M003','周禾','普通','澄川','2023-03-01','S02'),('M004','许星','金卡','青岚','2023-04-01','S03'),('M005','赵云','普通','青岚','2023-05-01','S03'),('M006','沈川','银卡','澄川','2023-06-01','S02');
INSERT INTO products VALUES ('SKU001','星河柚子茶','饮品',9.90),('SKU002','星河麦香包','烘焙',12.00),('SKU003','星河鲜果盒','生鲜',19.90);
INSERT INTO order_items VALUES ('O2026010001',1,'SKU001',1,89.70);
INSERT INTO order_items VALUES ('O2026010002',1,'SKU002',1,33.60);
INSERT INTO order_items VALUES ('O2026010003',1,'SKU003',1,13.50);
INSERT INTO order_items VALUES ('O2026010004',1,'SKU001',1,44.00);
INSERT INTO order_items VALUES ('O2026010005',1,'SKU002',1,120.40);
INSERT INTO order_items VALUES ('O2026020001',1,'SKU003',1,58.40);
INSERT INTO order_items VALUES ('O2026020002',1,'SKU001',1,29.70);
INSERT INTO order_items VALUES ('O2026020003',1,'SKU002',1,76.60);
INSERT INTO order_items VALUES ('O2026020004',1,'SKU003',1,24.00);
INSERT INTO order_items VALUES ('O2026020005',1,'SKU001',1,9.90);
INSERT INTO order_items VALUES ('O2026030001',1,'SKU002',1,95.70);
INSERT INTO order_items VALUES ('O2026030002',1,'SKU003',1,44.00);
INSERT INTO order_items VALUES ('O2026030003',1,'SKU001',1,36.00);
INSERT INTO order_items VALUES ('O2026030004',1,'SKU002',1,19.90);
INSERT INTO order_items VALUES ('O2026030005',1,'SKU003',1,61.40);
