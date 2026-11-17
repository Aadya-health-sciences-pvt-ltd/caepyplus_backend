"""Daily clear of workspace_doctor_dashboard leaves doctor_dashboard intact."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.linq360.dashboard.config.dashboard_service import DashboardService
from src.app.linq360.models.dashboard import DoctorDashboard, WorkspaceDoctorDashboard


@pytest.mark.asyncio
async def test_clear_all_workspace_dashboards_keeps_doctor_content(
    db_session: AsyncSession,
) -> None:
    content = {"reviews": {"pending": 2}}
    doctor = DoctorDashboard(ph_user_id=9001, todays_glance=content)
    rows = [
        WorkspaceDoctorDashboard(
            workspace_id=10,
            ph_user_id=9001,
            ws_user_id=100,
            appointment_json={"todays_schedule": [{"patient_name": "A"}]},
            requests={"count": 1},
            appointments={"count": 2},
        ),
        WorkspaceDoctorDashboard(
            workspace_id=11,
            ph_user_id=9002,
            ws_user_id=101,
            appointment_json={"todays_schedule": [{"patient_name": "B"}]},
            requests={"count": 0},
            appointments={"count": 1},
        ),
    ]
    db_session.add_all([doctor, *rows])
    await db_session.flush()

    deleted = await DashboardService(db_session).clear_all_workspace_dashboards()
    await db_session.flush()

    assert deleted >= 2
    remaining = (
        await db_session.execute(select(func.count()).select_from(WorkspaceDoctorDashboard))
    ).scalar_one()
    assert remaining == 0

    await db_session.refresh(doctor)
    assert doctor.todays_glance == content
