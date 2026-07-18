"""
migrate_departments.py — Data migration script for updated department names.

Run this script to update legacy department names to their new values in
Supabase (Profiles). (Google sheets reads directly from Supabase for users,
so just updating Supabase is enough if profiles are synced, but you may need to
update other sheets if they denormalize department, though currently it seems
only Supabase holds the single source of truth for user department).

Mappings:
  "Full-Stack" -> "Full Stack"
  "AI" -> "AI Engineer"
  "Social Business Analysis" -> "Business Analyst" (Default mapping, please review manually)
"""

import logging
from config import DEPARTMENTS
from services import supabase_service as supa

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAPPINGS = {
    "Full-Stack": "Full Stack",
    "AI": "AI Engineer",
    "Social Business Analysis": "Business Analyst",
}

def run_migration():
    logger.info("Starting Department migration...")
    
    # Supabase Profiles
    profiles = supa.get_all_profiles()
    migrated_count = 0
    
    for p in profiles:
        old_dept = p.get("department")
        if old_dept in MAPPINGS:
            new_dept = MAPPINGS[old_dept]
            try:
                supa.update_profile(p["id"], department=new_dept)
                logger.info(f"Updated user {p.get('email')} department: {old_dept} -> {new_dept}")
                migrated_count += 1
            except Exception as e:
                logger.error(f"Failed to update user {p.get('email')}: {e}")
                
    logger.info(f"Migration completed. Total profiles updated: {migrated_count}")
    logger.info(f"NOTE: 'Social Business Analysis' users were mapped to 'Business Analyst' by default.")
    logger.info(f"Please manually review them in the Admin portal if any should be 'Social Media' instead.")

if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():
        run_migration()
