import json
import unittest
from datetime import datetime, timedelta, timezone

from retail_intelligence.domain.identity import PipelineIdentity, canonical_configuration_json
from retail_intelligence.domain.media import TimeRange


class PipelineIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        start = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
        self.time_range = TimeRange(start, start + timedelta(seconds=10))
        self.configuration = {
            "sampling": {"frames": 80, "method": "even"},
            "models": ["detector-v1", "captioner-v2"],
        }

    def identity(self, **changes) -> PipelineIdentity:
        values = {
            "source_checksum": "sha256:source-a",
            "time_range": self.time_range,
            "pipeline_version": "pipeline-v3",
            "configuration": self.configuration,
        }
        values.update(changes)
        return PipelineIdentity(**values)

    def test_identical_inputs_reproduce_all_identifiers(self) -> None:
        first = self.identity()
        second = self.identity(configuration=json.dumps(self.configuration))

        self.assertEqual(first.configuration_id, second.configuration_id)
        self.assertEqual(first.evidence_window_id, second.evidence_window_id)
        self.assertEqual(first.pipeline_run_id, second.pipeline_run_id)
        self.assertEqual(
            first.observation_id("caption", 0), second.observation_id("caption", 0)
        )

    def test_mapping_order_and_sequence_serialization_do_not_change_identity(self) -> None:
        reordered = {
            "models": ("detector-v1", "captioner-v2"),
            "sampling": {"method": "even", "frames": 80.0},
        }

        self.assertEqual(
            self.identity().identity_digest,
            self.identity(configuration=reordered).identity_digest,
        )

    def test_each_identity_bearing_input_changes_identity(self) -> None:
        changes = (
            {"source_checksum": "sha256:source-b"},
            {
                "time_range": TimeRange(
                    self.time_range.start,
                    self.time_range.end + timedelta(seconds=1),
                )
            },
            {"pipeline_version": "pipeline-v4"},
            {"configuration": {"sampling": {"frames": 79, "method": "even"}}},
        )

        baseline = self.identity().identity_digest
        for change in changes:
            with self.subTest(change=tuple(change)):
                self.assertNotEqual(baseline, self.identity(**change).identity_digest)

    def test_observation_discriminator_changes_only_observation_identity(self) -> None:
        identity = self.identity()

        self.assertNotEqual(
            identity.observation_id("caption", 0),
            identity.observation_id("caption", 1),
        )
        self.assertNotEqual(identity.evidence_window_id, identity.pipeline_run_id)

    def test_credentials_and_signed_urls_are_excluded_from_configuration(self) -> None:
        first = {
            **self.configuration,
            "password": "first-password",
            "nested": {
                "authorization": "Bearer first-token",
                "media_url": "https://media.test/clip?X-Amz-Signature=first-signature",
            },
        }
        second = {
            **self.configuration,
            "password": "second-password",
            "nested": {
                "authorization": "Bearer second-token",
                "media_url": "https://media.test/clip?X-Amz-Signature=second-signature",
            },
        }

        canonical = canonical_configuration_json(first)
        self.assertEqual(
            self.identity(configuration=first).identity_digest,
            self.identity(configuration=second).identity_digest,
        )
        for sensitive_value in ("first-password", "first-token", "first-signature"):
            self.assertNotIn(sensitive_value, canonical)

    def test_invalid_configuration_error_does_not_echo_sensitive_value(self) -> None:
        sensitive_value = "do-not-print-this"

        with self.assertRaisesRegex(ValueError, "configuration") as raised:
            canonical_configuration_json({"safe": {sensitive_value}})

        self.assertNotIn(sensitive_value, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
