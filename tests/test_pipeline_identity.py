import json
import traceback
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
            "apiToken": "first-api-token",
            "nested": {
                "authorization": "Bearer first-token",
                "media_url": "https://media.test/clip?X-Amz-Signature=first-signature",
                "repository": "https://user:first-url-password@media.test/clip",
            },
        }
        second = {
            **self.configuration,
            "password": "second-password",
            "apiToken": "second-api-token",
            "nested": {
                "authorization": "Bearer second-token",
                "media_url": "https://media.test/clip?X-Amz-Signature=second-signature",
                "repository": "https://user:second-url-password@media.test/clip",
            },
        }

        canonical = canonical_configuration_json(first)
        self.assertEqual(
            self.identity(configuration=first).identity_digest,
            self.identity(configuration=second).identity_digest,
        )
        for sensitive_value in (
            "first-password",
            "first-api-token",
            "first-token",
            "first-signature",
            "first-url-password",
        ):
            self.assertNotIn(sensitive_value, canonical)

    def test_configuration_key_containing_token_word_is_not_a_credential(self) -> None:
        first = canonical_configuration_json({"tokenizer": "revision-1"})
        second = canonical_configuration_json({"tokenizer": "revision-2"})

        self.assertNotEqual(first, second)

    def test_ordinary_query_parameter_is_not_treated_as_a_signature(self) -> None:
        canonical = canonical_configuration_json(
            {"schema": "https://example.test/config?design=compact"}
        )

        self.assertIn("design=compact", canonical)

    def test_signed_url_resource_path_remains_identity_bearing(self) -> None:
        first = {"media_url": "https://media.test/first?X-Amz-Signature=secret"}
        second = {"media_url": "https://media.test/second?X-Amz-Signature=secret"}

        first_canonical = canonical_configuration_json(first)
        self.assertIn("https://media.test/first", first_canonical)
        self.assertNotIn("X-Amz-Signature", first_canonical)
        self.assertNotEqual(
            self.identity(configuration=first).identity_digest,
            self.identity(configuration=second).identity_digest,
        )

    def test_invalid_configuration_error_and_traceback_do_not_echo_input(self) -> None:
        sensitive_value = "do-not-print-this"

        with self.assertRaisesRegex(ValueError, "configuration") as raised:
            canonical_configuration_json('{"password":"do-not-print-this", invalid}')

        self.assertNotIn(sensitive_value, str(raised.exception))
        rendered_traceback = "".join(
            traceback.format_exception(raised.exception)
        )
        self.assertNotIn(sensitive_value, rendered_traceback)

    def test_duplicate_serialized_configuration_keys_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid JSON object"):
            canonical_configuration_json('{"sampling": 80, "sampling": 79}')


if __name__ == "__main__":
    unittest.main()
