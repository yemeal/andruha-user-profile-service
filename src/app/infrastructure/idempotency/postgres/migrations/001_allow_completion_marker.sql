-- Existing installations: apply before enabling COMPLETION_ONLY on any worker.
-- Fresh schemas already contain this constraint in IdempotencyRecordORM.
-- No rows are removed or replay identities changed.
ALTER TABLE idempotency_records
    DROP CONSTRAINT ck_idempotency_records_replayable_result,
    ADD CONSTRAINT ck_idempotency_records_replayable_result CHECK (
        (
            result_type = 'completion'
            AND result_payload IS NULL
            AND resource_type IS NULL
            AND resource_id IS NULL
            AND resource_version IS NULL
        )
        OR
        (
            result_type <> 'completion'
            AND (
                result_payload IS NOT NULL
                OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)
            )
        )
    );
