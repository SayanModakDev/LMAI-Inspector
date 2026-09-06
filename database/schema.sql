CREATE DATABASE IF NOT EXISTS legal_metrology_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE legal_metrology_db;

CREATE TABLE IF NOT EXISTS users (
    id INT NOT NULL AUTO_INCREMENT,
    username VARCHAR(100) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'inspector',
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_username (username)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS inspections (
    id INT NOT NULL AUTO_INCREMENT,
    inspection_date DATETIME NULL,
    product_name VARCHAR(255) NULL,
    brand VARCHAR(255) NULL,
    product_type VARCHAR(100) NULL,
    category VARCHAR(50) NULL,
    category_confidence FLOAT NULL,
    package_type VARCHAR(50) DEFAULT 'RETAIL',
    import_status VARCHAR(50) DEFAULT 'DOMESTIC',
    quantity_type VARCHAR(50) NULL,
    overall_result VARCHAR(50) NULL,
    priority VARCHAR(20) DEFAULT 'MEDIUM',
    image_path VARCHAR(500) NULL,
    processed_image_path VARCHAR(500) NULL,
    inspector_name VARCHAR(255) DEFAULT 'Default Inspector',
    inspector_id INT NULL,
    notes TEXT NULL,
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_inspections_inspector_id (inspector_id),
    CONSTRAINT fk_inspections_inspector_id
        FOREIGN KEY (inspector_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS inspection_images (
    id INT NOT NULL AUTO_INCREMENT,
    inspection_id INT NOT NULL,
    image_index INT NOT NULL,
    file_name VARCHAR(500) NOT NULL,
    processed_file_name VARCHAR(500) NULL,
    source VARCHAR(30) DEFAULT 'UPLOAD',
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_inspection_images_inspection_id (inspection_id),
    CONSTRAINT fk_inspection_images_inspection_id
        FOREIGN KEY (inspection_id) REFERENCES inspections (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS products (
    id INT NOT NULL AUTO_INCREMENT,
    inspection_id INT NOT NULL,
    product_name VARCHAR(255) NULL,
    brand VARCHAR(255) NULL,
    generic_name VARCHAR(255) NULL,
    manufacturer VARCHAR(500) NULL,
    packer VARCHAR(500) NULL,
    importer VARCHAR(500) NULL,
    address TEXT NULL,
    country_of_origin VARCHAR(100) NULL,
    declared_net_quantity_value VARCHAR(50) NULL,
    declared_net_quantity_unit VARCHAR(20) NULL,
    mrp VARCHAR(50) NULL,
    manufacture_date VARCHAR(100) NULL,
    packing_date VARCHAR(100) NULL,
    import_date VARCHAR(100) NULL,
    best_before VARCHAR(100) NULL,
    use_by VARCHAR(100) NULL,
    consumer_care TEXT NULL,
    unit_sale_price VARCHAR(50) NULL,
    ingredients TEXT NULL,
    dimensions VARCHAR(100) NULL,
    actual_measured_weight FLOAT NULL,
    actual_weight_unit VARCHAR(20) NULL,
    measurement_source VARCHAR(50) NULL,
    measurement_timestamp DATETIME NULL,
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_products_inspection_id (inspection_id),
    CONSTRAINT fk_products_inspection_id
        FOREIGN KEY (inspection_id) REFERENCES inspections (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ocr_results (
    id INT NOT NULL AUTO_INCREMENT,
    inspection_id INT NOT NULL,
    raw_text TEXT NULL,
    ocr_data JSON NULL,
    ocr_engine VARCHAR(50) DEFAULT 'PaddleOCR',
    processing_time_ms INT NULL,
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_ocr_results_inspection_id (inspection_id),
    CONSTRAINT fk_ocr_results_inspection_id
        FOREIGN KEY (inspection_id) REFERENCES inspections (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS extracted_fields (
    id INT NOT NULL AUTO_INCREMENT,
    inspection_id INT NOT NULL,
    field_name VARCHAR(100) NOT NULL,
    field_value TEXT NULL,
    confidence FLOAT NULL,
    source VARCHAR(50) DEFAULT 'OCR',
    extraction_method VARCHAR(100) NULL,
    bbox JSON NULL,
    source_image_id INT NULL,
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_extracted_fields_inspection_id (inspection_id),
    CONSTRAINT fk_extracted_fields_inspection_id
        FOREIGN KEY (inspection_id) REFERENCES inspections (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rules (
    id INT NOT NULL AUTO_INCREMENT,
    rule_id VARCHAR(50) NOT NULL,
    parameter VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    package_type VARCHAR(50) DEFAULT 'ALL',
    product_type VARCHAR(100) DEFAULT 'ALL',
    regulatory_source VARCHAR(100) DEFAULT 'LEGAL_METROLOGY',
    `condition` VARCHAR(50) DEFAULT 'APPLICABLE',
    rule_reference VARCHAR(255) NULL,
    source_document VARCHAR(500) NULL,
    rule_version VARCHAR(50) DEFAULT 'PENDING_VERIFICATION',
    effective_from VARCHAR(20) NULL,
    effective_until VARCHAR(20) NULL,
    required BOOLEAN DEFAULT TRUE,
    what_to_extract VARCHAR(100) NULL,
    validation_method VARCHAR(100) NULL,
    verification_type VARCHAR(50) NULL,
    result_type VARCHAR(50) DEFAULT 'PASS_FAIL',
    severity VARCHAR(20) DEFAULT 'HIGH',
    exception TEXT NULL,
    evidence_required BOOLEAN DEFAULT TRUE,
    source_link VARCHAR(500) NULL,
    detection_method VARCHAR(100) NULL,
    visual_or_text VARCHAR(30) DEFAULT 'TEXT',
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_rules_rule_id (rule_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rule_results (
    id INT NOT NULL AUTO_INCREMENT,
    inspection_id INT NOT NULL,
    rule_id VARCHAR(50) NOT NULL,
    parameter VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    message TEXT NULL,
    evidence_data JSON NULL,
    rule_version VARCHAR(50) NULL,
    regulatory_source VARCHAR(100) NULL,
    rule_reference VARCHAR(255) NULL,
    review_required BOOLEAN DEFAULT FALSE,
    inspector_note TEXT NULL,
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_rule_results_inspection_id (inspection_id),
    CONSTRAINT fk_rule_results_inspection_id
        FOREIGN KEY (inspection_id) REFERENCES inspections (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS evidence (
    id INT NOT NULL AUTO_INCREMENT,
    inspection_id INT NOT NULL,
    rule_id VARCHAR(50) NULL,
    parameter VARCHAR(100) NULL,
    evidence_type VARCHAR(50) DEFAULT 'OCR_TEXT',
    text_content TEXT NULL,
    bbox JSON NULL,
    confidence FLOAT NULL,
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_evidence_inspection_id (inspection_id),
    CONSTRAINT fk_evidence_inspection_id
        FOREIGN KEY (inspection_id) REFERENCES inspections (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reports (
    id INT NOT NULL AUTO_INCREMENT,
    inspection_id INT NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    generated_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_reports_inspection_id (inspection_id),
    CONSTRAINT fk_reports_inspection_id
        FOREIGN KEY (inspection_id) REFERENCES inspections (id)
) ENGINE=InnoDB;
