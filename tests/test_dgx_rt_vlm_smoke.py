import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_dgx_rt_vlm_smoke import (
    EXPECTED_FRAME_COUNT,
    RTVLMSmokeClient,
    SmokeTestError,
)


class FakeRequester:
    def __init__(self, *, frame_count=EXPECTED_FRAME_COUNT, caption="A person walks away."):
        self.frame_count = frame_count
        self.caption = caption
        self.calls = []
        self.caption_calls = 0
        self.cleanup_succeeds = True

    def __call__(self, method, path, headers, body, content_type, timeout):
        self.calls.append((method, path, headers, body, content_type, timeout))
        if (method, path) == ("GET", "/v1/health/ready"):
            return {"ready": True}
        if (method, path) == ("GET", "/v1/models"):
            return {"data": [{"id": "nim_test_model"}]}
        if (method, path) == ("GET", "/v1/version"):
            return {"release": "3.2.1", "api": "3.1.0"}
        if (method, path) == ("POST", "/v1/files"):
            return {"id": "uploaded-file"}
        if (method, path) == ("POST", "/v1/generate_captions"):
            self.caption_calls += 1
            return {
                "chunk_responses": [
                    {
                        "content": self.caption,
                        "frame_count": self.frame_count,
                        "start_time": 0.0,
                        "end_time": 10.777,
                    }
                ]
            }
        if (method, path) == ("DELETE", "/v1/files/uploaded-file"):
            return {"deleted": self.cleanup_succeeds}
        raise AssertionError(f"unexpected request: {method} {path}")


class RTVLMSmokeClientTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.video_path = Path(self.temp_directory.name) / "fixture.mp4"
        self.video_path.write_bytes(b"video bytes")

    def test_runs_two_explicit_caption_requests_and_deletes_upload(self):
        requester = FakeRequester()
        client = RTVLMSmokeClient(
            "http://localhost:8018", "test-secret", requester=requester
        )

        client.ready()
        metadata = client.metadata()
        results = client.caption_twice(self.video_path, metadata["model"])

        self.assertEqual(metadata, {"model": "nim_test_model", "release": "3.2.1", "api": "3.1.0"})
        self.assertEqual(len(results), 2)
        self.assertEqual([result.frame_count for result in results], [80, 80])
        self.assertEqual(requester.caption_calls, 2)
        self.assertEqual(requester.calls[-1][0:2], ("DELETE", "/v1/files/uploaded-file"))
        self.assertNotIn("Authorization", requester.calls[0][2])
        for call in requester.calls[1:]:
            self.assertEqual(call[2]["Authorization"], "Bearer test-secret")

        first_caption_call = next(
            call for call in requester.calls if call[0:2] == ("POST", "/v1/generate_captions")
        )
        payload = json.loads(first_caption_call[3])
        self.assertEqual(payload["num_frames_per_second_or_fixed_frames_chunk"], 80)
        self.assertFalse(payload["use_fps_for_chunking"])
        self.assertEqual((payload["vlm_input_width"], payload["vlm_input_height"]), (448, 448))

    def test_wrong_reported_frame_count_fails_and_deletes_upload(self):
        requester = FakeRequester(frame_count=79)
        client = RTVLMSmokeClient(
            "http://localhost:8018", "test-secret", requester=requester
        )

        with self.assertRaisesRegex(SmokeTestError, "reported 79 frames"):
            client.caption_twice(self.video_path, "nim_test_model")

        self.assertEqual(requester.calls[-1][0:2], ("DELETE", "/v1/files/uploaded-file"))

    def test_empty_caption_fails_and_deletes_upload(self):
        requester = FakeRequester(caption="  ")
        client = RTVLMSmokeClient(
            "http://localhost:8018", "test-secret", requester=requester
        )

        with self.assertRaisesRegex(SmokeTestError, "caption response has no content"):
            client.caption_twice(self.video_path, "nim_test_model")

        self.assertEqual(requester.calls[-1][0:2], ("DELETE", "/v1/files/uploaded-file"))

    def test_rejects_base_urls_that_could_expose_credentials(self):
        for base_url in (
            "http://user:password@localhost:8018",
            "http://localhost:8018/v1",
            "http://localhost:8018?token=secret",
        ):
            with self.subTest(base_url=base_url):
                with self.assertRaisesRegex(ValueError, "without credentials"):
                    RTVLMSmokeClient(base_url, "test-secret")


if __name__ == "__main__":
    unittest.main()
