import os
import sys
from sqlalchemy.orm import declarative_base

# Add src to path so we can import our models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from app.models.doctor import Doctor
from app.models.onboarding import DoctorIdentity, DoctorMedia, DoctorStatusHistory, DropdownOption
from app.models.user import User

print("# Database Schema Documentation\n")
print("*Auto-generated from current SQLAlchemy models.* \n")

models = [Doctor, DoctorIdentity, DoctorMedia, DoctorStatusHistory, DropdownOption, User]

for model in models:
    print(f"## Table: `{model.__tablename__}`\n")
    print("| Column | Type | Nullable | Primary / Foreign Key |")
    print("|--------|------|----------|-----------------------|")
    for column in model.__table__.columns:
        pk = "PK" if column.primary_key else ""
        fk = f"FK -> {list(column.foreign_keys)[0].target_fullname}" if column.foreign_keys else ""
        keys = []
        if pk: keys.append(pk)
        if fk: keys.append(fk)
        key_str = ", ".join(keys)
        
        type_str = str(column.type)
        null_str = "Yes" if column.nullable else "No"
        print(f"| `{column.name}` | `{type_str}` | {null_str} | {key_str} |")
    print("\n")
