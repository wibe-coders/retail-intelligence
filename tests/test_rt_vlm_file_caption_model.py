import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from retail_intelligence.adapters.nvidia import (
    RTVLMFileCaptionModel,
    RTVLMServiceError,
)
from retail_intelligence.domain.media import (
    FrameRange,
    RetentionClass,
    Source,
    SourceClock,
    SourceReference,
)


UPLOAD_ID = "11111111-1111-4111-8111-111111111111"
CAPTION_ID = "22222222-2222-4222-8222-222222222222"


class FakeRequester:
    def __init__(self, *, caption_text: str = "A person walks down a passageway.") -> None:
        self.caption_text = caption_text
        self.calls = []

    def __call__(self, method, path, headers, body, content_type, timeout):
        self.calls.append((method, path, headers, body, content_type, timeout))
        if (method, path) == ("GET", "/v1/health/ready"):
            return {"ready": True}
        if (method, path) == ("GET", "/v1/models"):
            return {"data": [{"id": "nim_test_model"}]}
        if (method, path) == ("GET", "/v1/version"):
            return {"release": "3.2.1", "api": "3.1.0"}
        if (method, path) == ("POST", "/v1/files"):
            return {"id": UPLOAD_ID}
        if (method, path) == ("POST", "/v1/generate_captions"):
            return {
                "id": CAPTION_ID,
                "chunk_responses": [
                    {
                        "content": self.caption_text,
                        "frame_count": 80,
                        "start_time": 0.0,
                        "end_time": 10.777,
                    }
                ],
            }
        if (method, path) == ("DELETE", f"/v1/files/{UPLOAD_ID}"):
            return {"deleted": True}
        raise AssertionError(f"unexpected request: {method} {path}")


class RTVLMFileCaptionModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.path = Path(self.temp_directory.name) / "clip.mp4"
        self.path.write_bytes(b"bounded video bytes")
        self.source = Source(
            "source-one",
            SourceReference("store-one", "camera-one", "recording-one"),
            str(self.path),
            "h264",
            960,
            540,
            30000 / 1001,
            RetentionClass.STANDARD,
            "sha256:test",
            FrameRange(0, 323),
            SourceClock(
                datetime(2026, 8, 16, tzinfo=timezone.utc),
                0,
                323,
                1001,
                30000,
            ),
        )

    def test_uploads_captions_and_deletes_with_explicit_target_settings(self) -> None:
        requester = FakeRequester()
        model = RTVLMFileCaptionModel(
            "http://localhost:8018",
            "test-secret",
            requester=requester,
        )

        model.ready()
        result = model.caption(self.source, "window-one")

        self.assertEqual(result.text, "A person walks down a passageway.")
        self.assertEqual(result.model, "nim_test_model")
        self.assertEqual(result.model_version, "3.2.1")
        self.assertEqual(
            result.vendor_output_reference,
            f"vendor-output://rt-vlm/{CAPTION_ID}",
        )
        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.last_frame_counts, (80,))
        self.assertTrue(model.last_upload_deleted)
        self.assertIsNotNone(model.last_latency_seconds)

        request_pairs = [(call[0], call[1]) for call in requester.calls]
        self.assertEqual(
            request_pairs,
            [
                ("GET", "/v1/health/ready"),
                ("GET", "/v1/models"),
                ("GET", "/v1/version"),
                ("POST", "/v1/files"),
                ("POST", "/v1/generate_captions"),
                ("DELETE", f"/v1/files/{UPLOAD_ID}"),
            ],
        )
        self.assertNotIn("Authorization", requester.calls[0][2])
        for call in requester.calls[1:]:
            self.assertEqual(call[2]["Authorization"], "Bearer test-secret")

        upload_call = requester.calls[3]
        self.assertTrue(upload_call[4].startswith("multipart/form-data; boundary="))
        self.assertIn(b"bounded video bytes", upload_call[3])
        self.assertIn(b'name="purpose"', upload_call[3])
        self.assertIn(b"vision", upload_call[3])
        self.assertIn(b'name="media_type"', upload_call[3])

        caption_request = json.loads(requester.calls[4][3])
        self.assertEqual(
            caption_request,
            {
                "id": UPLOAD_ID,
                "model": "nim_test_model",
                "prompt": (
                    "Describe only the visible actions and setting in this video. "
                    "Do not infer identity or intent."
                ),
                "chunk_duration": 12,
                "stream": False,
                "num_frames_per_second_or_fixed_frames_chunk": 80,
                "use_fps_for_chunking": False,
                "vlm_input_width": 448,
                "vlm_input_height": 448,
            },
        )

    def test_empty_caption_fails_but_still_deletes_the_upload(self) -> None:
        requester = FakeRequester(caption_text="  ")
        model = RTVLMFileCaptionModel(
            "http://localhost:8018",
            "test-secret",
            requester=requester,
        )

        with self.assertRaisesRegex(RTVLMServiceError, "contains no text"):
            model.caption(self.source, "window-one")

        self.assertEqual(
            (requester.calls[-1][0], requester.calls[-1][1]),
            ("DELETE", f"/v1/files/{UPLOAD_ID}"),
        )
        self.assertTrue(model.last_upload_deleted)

    def test_rejects_an_oversized_file_before_contacting_the_service(self) -> None:
        requester = FakeRequester()
        model = RTVLMFileCaptionModel(
            "http://localhost:8018",
            "test-secret",
            max_upload_bytes=1,
            requester=requester,
        )

        with self.assertRaisesRegex(ValueError, "exceeds"):
            model.caption(self.source, "window-one")

        self.assertEqual(requester.calls, [])

    def test_rejects_an_empty_file_before_contacting_the_service(self) -> None:
        self.path.write_bytes(b"")
        requester = FakeRequester()
        model = RTVLMFileCaptionModel(
            "http://localhost:8018",
            "test-secret",
            requester=requester,
        )

        with self.assertRaisesRegex(ValueError, "must not be empty"):
            model.caption(self.source, "window-one")
        self.assertEqual(requester.calls, [])

    def test_rejects_base_urls_that_could_expose_credentials(self) -> None:
        for base_url in (
            "http://user:password@localhost:8018",
            "http://localhost:8018?key=secret",
            "http://localhost:8018/unexpected-prefix",
        ):
            with self.subTest(base_url=base_url):
                with self.assertRaisesRegex(ValueError, "without credentials, path"):
                    RTVLMFileCaptionModel(base_url, "test-secret")


if __name__ == "__main__":
    unittest.main()
