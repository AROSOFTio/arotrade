#!/usr/bin/env python3
"""
Create an admin user for AroTrade AI.
Run this script after migrations are applied.

Usage:
    python scripts/create_admin.py
"""
import os
import sys
import getpass
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import DATABASE_URL
from app.database import Base
from app import models
from app.auth import hash_password, validate_password

def create_admin():
    """Create admin user interactively."""
    print("\n" + "="*50)
    print("AroTrade AI - Admin User Creation")
    print("="*50 + "\n")

    # Get input
    email = input("Enter admin email: ").strip()
    full_name = input("Enter admin full name (optional): ").strip()

    while True:
        password = getpass.getpass("Enter admin password: ")
        if not validate_password(password):
            print("\n❌ Password does not meet requirements:")
            print("   - Minimum 8 characters")
            print("   - Must include uppercase letter")
            print("   - Must include number")
            print("   - Must include special character (!@#$%^&*()_+-=[]{}|;:,.<>?)")
            continue

        confirm = getpass.getpass("Confirm password: ")
        if password == confirm:
            break
        print("❌ Passwords do not match\n")

    # Create database session
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Check if user exists
        existing = session.query(models.User).filter(
            models.User.email == email
        ).first()

        if existing:
            print(f"\n❌ User with email {email} already exists")
            return False

        # Create admin user
        admin = models.User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name or "",
            role=models.UserRole.ADMIN,
            is_active=True,
            is_verified=True,
            accepted_risk_disclaimer=True,
            accepted_live_disclaimer=True,
        )

        session.add(admin)
        session.commit()

        print(f"\n✅ Admin user created successfully!")
        print(f"   Email: {email}")
        print(f"   Role: Admin")
        print(f"   Status: Active\n")

        return True

    except Exception as e:
        print(f"\n❌ Error creating admin user: {e}\n")
        session.rollback()
        return False
    finally:
        session.close()


if __name__ == "__main__":
    success = create_admin()
    sys.exit(0 if success else 1)
