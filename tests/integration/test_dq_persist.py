from datetime import UTC, datetime

from sqlalchemy import delete

from mq.db.models import DQResult as DQResultRow
from mq.db.session import session_scope
from mq.pipelines.dq import DQCheckResult, persist_results


def test_persist_results_writes_rows() -> None:
    run_at = datetime.now(UTC)
    results = [
        DQCheckResult(check_id="DQ01", dataset="test_dataset", status="pass", details={}),
        DQCheckResult(
            check_id="DQ03", dataset="test_dataset", status="fail", details={"bad_count": 3}
        ),
    ]
    persist_results(results, run_at=run_at)

    with session_scope() as session:
        rows = (
            session.query(DQResultRow)
            .filter(DQResultRow.dataset == "test_dataset", DQResultRow.run_at == run_at)
            .all()
        )
        assert {r.check_id for r in rows} == {"DQ01", "DQ03"}
        fail_row = next(r for r in rows if r.check_id == "DQ03")
        assert fail_row.status == "fail"
        assert fail_row.details == {"bad_count": 3}

        # cleanup — these are test rows
        session.execute(delete(DQResultRow).where(DQResultRow.dataset == "test_dataset"))
