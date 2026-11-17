CREATE DATABASE lanting_shop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE lanting_shop;
CREATE TABLE `members` (`member_no` VARCHAR(16) NOT NULL COMMENT '会员编号',`member_name` VARCHAR(64) NOT NULL COMMENT '会员姓名',`member_level` VARCHAR(8) NOT NULL COMMENT '会员等级：普通/金卡',`joined_on` DATE NOT NULL COMMENT '入会日期',PRIMARY KEY (`member_no`)) COMMENT='会员';
-- No channel column: the material's 下单渠道 has nothing to bind to (AC-04).
CREATE TABLE `orders` (`order_no` VARCHAR(20) NOT NULL COMMENT '订单号',`member_no` VARCHAR(16) NOT NULL COMMENT '下单会员',`item_count` INTEGER NOT NULL COMMENT '件数',`pay_amount` DECIMAL(12, 2) NOT NULL COMMENT '实付金额',`ordered_at` DATETIME NOT NULL COMMENT '下单时间',`status` VARCHAR(8) NOT NULL COMMENT '订单状态：待支付/已支付/已取消',PRIMARY KEY (`order_no`)) COMMENT='订单';
-- Not synced in the first round (AC-10); the material calls the column ship_qty, it is qty.
CREATE TABLE `shipments` (`shipment_no` VARCHAR(20) NOT NULL COMMENT '发货单号',`order_no` VARCHAR(20) NOT NULL COMMENT '订单号',`qty` INTEGER NOT NULL COMMENT '发货数量',`shipped_at` DATETIME NOT NULL COMMENT '发货时间',PRIMARY KEY (`shipment_no`)) COMMENT='发货单';
INSERT INTO members VALUES ('M101','林汀','金卡','2025-06-01'),('M102','周澄','普通','2025-08-15'),('M103','许岚','普通','2025-11-02');
INSERT INTO orders VALUES
 ('O-1001','M101',3,5280.00,'2026-03-01 10:20:00','已支付'),
 ('O-1002','M102',1,36.00,'2026-03-01 14:05:00','已支付'),
 ('O-1003','M103',2,58.50,'2026-03-02 09:40:00','待支付'),
 ('O-1004','M102',5,120.00,'2026-03-03 16:30:00','已取消');
INSERT INTO shipments VALUES ('F-1001','O-1001',3,'2026-03-02 09:00:00'),('F-1002','O-1002',1,'2026-03-02 11:00:00');
