import os
from pathlib import Path
import pytest


def test_nextjs_build_artifacts():
    """Verify that Next.js production build generated all required pages and assets."""
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    next_dir = frontend_dir / ".next"

    assert next_dir.exists(), "Next.js .next directory must exist after build"

    # Verify server app pages
    server_app_dir = next_dir / "server" / "app"
    assert server_app_dir.exists()

    expected_routes = [
        "index.html",              # /
        "ledger.html",             # /ledger
        "forecasts.html",          # /forecasts
        "purchase-orders.html",    # /purchase-orders
        "alerts.html",             # /alerts
        "autonomy-settings.html",  # /autonomy-settings
    ]

    for route in expected_routes:
        page_file = server_app_dir / route
        assert page_file.exists(), f"Route artifact {route} must be compiled in {server_app_dir}"
        assert page_file.stat().st_size > 0


def test_frontend_routes_configuration():
    """Verify that all main dashboard routes and components exist in source code."""
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

    required_source_files = [
        "app/layout.tsx",
        "app/page.tsx",
        "app/ledger/page.tsx",
        "app/forecasts/page.tsx",
        "app/purchase-orders/page.tsx",
        "app/alerts/page.tsx",
        "app/autonomy-settings/page.tsx",
        "components/Navbar.tsx",
        "lib/api.ts",
    ]

    for rel_path in required_source_files:
        p = frontend_dir / rel_path
        assert p.exists(), f"Source file {rel_path} must exist"
        content = p.read_text(encoding="utf-8")
        assert len(content) > 100
