import os
from pathlib import Path
from typing import List, Optional, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # General Environment
    PROJECT_NAME: str = "Autonomous Inventory Management System"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ]

    # Database Settings
    # Primary is PostgreSQL; local fallback can be SQLite
    DATABASE_URL: str = "sqlite+aiosqlite:///./inventory.db"
    SYNC_DATABASE_URL: str = "sqlite:///./inventory.db"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "inventory_db"

    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Security & JWT Auth
    JWT_SECRET_KEY: str = "development-secret-key-at-least-32-characters-long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Shopify Webhook Secret
    SHOPIFY_WEBHOOK_SECRET: str = "shpss_example_secret_for_hmac_sha256_verification"

    # Supplier Gateway & Notifications
    SUPPLIER_MOCK_API_URL: str = "http://localhost:8000/api/v1/suppliers/mock-endpoint"
    SMTP_HOST: str = "smtp.mailtrap.io"
    SMTP_PORT: int = 2525
    SMTP_USER: str = "mock_user"
    SMTP_PASSWORD: str = "mock_pass"
    SMTP_FROM_EMAIL: str = "procurement@autonomous-inventory.local"
    SLACK_WEBHOOK_URL: Optional[str] = None

    # MLflow Tracking
    MLFLOW_TRACKING_URI: str = "file:./mlruns"
    MLFLOW_EXPERIMENT_NAME: str = "demand_forecasting"

    # Storage Paths
    STORAGE_DIR: str = "./storage"
    PO_PDF_DIR: str = "./storage/purchase_orders"

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.DATABASE_URL.lower()


settings = Settings()

# Ensure storage directories exist
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.PO_PDF_DIR, exist_ok=True)

