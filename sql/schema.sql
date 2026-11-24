-- Audit records: one row per committed state transition. write_id is unique per DynamoDB write,
-- so a double-applied transition shows up as two rows instead of being silently merged.
CREATE TABLE IF NOT EXISTS audit_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  write_id CHAR(32) NOT NULL UNIQUE,
  case_id VARCHAR(40) NOT NULL,
  round_no INT NOT NULL,
  from_state VARCHAR(24) NOT NULL,
  to_state VARCHAR(24) NOT NULL,
  actor VARCHAR(64) NOT NULL,
  reason VARCHAR(255) NOT NULL DEFAULT '',
  detail JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY idx_case (case_id, id)
);

-- What each worker received from SQS (for the learn page and for ordering tests).
CREATE TABLE IF NOT EXISTS queue_receipts (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  case_id VARCHAR(40) NOT NULL,
  round_no INT NOT NULL,
  message_id VARCHAR(64) NOT NULL,
  group_id VARCHAR(64) NOT NULL,
  sequence_number VARCHAR(40) NOT NULL DEFAULT '',
  receive_count INT NOT NULL,
  worker_id VARCHAR(64) NOT NULL,
  body JSON NOT NULL,
  outcome VARCHAR(32) NOT NULL DEFAULT 'received',
  received_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY idx_case (case_id),
  KEY idx_group (group_id, id)
);
-- One row every time extraction actually ran (the expensive step).
CREATE TABLE IF NOT EXISTS extraction_runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  case_id VARCHAR(40) NOT NULL,
  round_no INT NOT NULL,
  worker_id VARCHAR(64) NOT NULL,
  engine VARCHAR(32) NOT NULL,
  started_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY idx_case (case_id)
);
