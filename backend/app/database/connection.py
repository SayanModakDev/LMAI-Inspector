"""
SQLAlchemy database connection and session management.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import get_settings

settings = get_settings()

# Keep MySQL as the production implementation, but use a local SQLite database
# when DATABASE_ENABLED=false so API and pipeline checks do not require MySQL.
database_url = settings.DATABASE_URL if settings.DATABASE_ENABLED else "sqlite:///./legal_metrology_dev.db"
engine_options = {"echo": settings.DEBUG}
if database_url.startswith("mysql"):
    engine_options.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
else:
    engine_options.update(connect_args={"check_same_thread": False})

engine = create_engine(database_url, **engine_options)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base for ORM models
Base = declarative_base()


def get_db():
    """
    FastAPI dependency that yields a database session.
    Ensures session is closed after request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Create all tables defined in models.
    Called once at application startup.
    """
    # Import models so Base.metadata knows about them
    import app.database.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns():
    """Apply additive columns for existing development databases."""
    additions = {
        "inspections": {
            "brand": "VARCHAR(255)",
            "product_type": "VARCHAR(100)",
            "regulatory_snapshot": "VARCHAR(255)",
        },
        "extracted_fields": {
            "source_image_id": "INTEGER",
            "extraction_method": "VARCHAR(100)",
        },
        "rules": {
            "product_type": "VARCHAR(100)",
            "regulatory_source": "VARCHAR(100)",
            "source_link": "VARCHAR(500)",
            "detection_method": "VARCHAR(100)",
            "visual_or_text": "VARCHAR(30)",
            "source_authority": "VARCHAR(255)",
            "source_url": "VARCHAR(500)",
            "rule_reference_status": "VARCHAR(50)",
            "instrument": "VARCHAR(255)",
            "citation": "VARCHAR(255)",
            "citation_text": "TEXT",
            "verification_status": "VARCHAR(50)",
            "version_date": "VARCHAR(20)",
            "effective_date": "VARCHAR(20)",
            "publication_date": "VARCHAR(20)",
            "applicability": "VARCHAR(255)",
            "screening_scope": "TEXT",
            "physical_scope": "TEXT",
            "notes": "TEXT",
        },
        "rule_results": {
            "regulatory_source": "VARCHAR(100)",
            "rule_reference": "VARCHAR(255)",
            "rule_reference_status": "VARCHAR(50)",
            "citation": "VARCHAR(255)",
            "verification_status": "VARCHAR(50)",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
