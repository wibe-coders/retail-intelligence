# RET-56 DGX Spark RT-VLM smoke test

Test date: **2026-08-16 UTC**
Result: **PASS for approved-file validation and standalone RT-VLM file inference**

## What this test proves

This test proves that one approved repository video can be validated, uploaded to the standalone
NVIDIA RT-VLM service on a DGX Spark, decoded and sampled for the configured inference budget, and
captioned twice by a local Cosmos3 Nano Reasoner without restarting the service.

```text
approved local MP4
  -> repository checksum, metadata, full-decode, sampling, and token checks
  -> RT-VLM file upload
  -> one 12-second inference chunk covering the 10.777-second video
  -> 80 evenly spaced 448x448 frames / 7,840 visual tokens
  -> local Cosmos3 Nano Reasoner inference
  -> timestamped caption response
  -> repeat on the same service instance
  -> delete the uploaded service copy
```

The run crossed both relevant boundaries:

1. `scripts/preflight_smoke_video.py` validated the repository fixture and its planned inference
   input.
2. RT-VLM accepted the file through `POST /v1/files` and returned non-empty captions through
   `POST /v1/generate_captions`.

This is not evidence that the complete application pipeline is production-ready. It did not run
the durable `VerticalSlice`, evidence indexing, source-scoped question answering, RTSP recovery,
or the four-hour full-stack soak required by the specifications. It validates the real local video
and VLM boundary that the fake-adapter tests do not cover.

## Tested system

| Item | Tested value |
|---|---|
| Host | NVIDIA DGX Spark / NVIDIA GB10 / `aarch64` |
| DGX OS | 7.5.0 |
| NVIDIA driver | 580.173.02 |
| CUDA reported by `nvidia-smi` | 13.0 |
| Docker | 29.2.1, build a5c7197 |
| Docker Compose | v5.0.2 |
| RT-VLM image | `nvcr.io/nvidia/vss-core/vss-rt-vlm:3.2.1-sbsa` |
| Image digest | `nvcr.io/nvidia/vss-core/vss-rt-vlm@sha256:026d45f462a7f349b019770193fd46bd7a5863bf8f06dc8586d8c8d6e900813f` |
| RT-VLM release / API | 3.2.1 / 3.1.0 |
| Model | `nim_nvidia_cosmos3-nano-reasoner_bf16-final` |
| Host API port | 8018 mapped to container port 8000 |
| vLLM memory utilization | 0.3 |

Peak memory is unavailable. `nvidia-smi` on this GB10 reported `Memory-Usage: Not Supported`, so
this report does not estimate it.

## Approved input

The repository fixture is `samples/hong-kong-passageway.mp4`.

| Property | Expected and observed value |
|---|---|
| SHA-256 | `8fef7d87a037714d2fc97f19faeac28a3ea41912d00fcced7032cc0674153dd4` |
| Encoding | H.264, YUV 4:2:0 |
| Encoded size | 960x540 |
| Frame rate | 30000/1001 FPS |
| Duration | 10.777433 seconds |
| Decoded frames | 323, all distinct |
| Sample | 80 unique frames spanning decoded indices 0 through 322 |
| Inference input | 448x448, 80 frames, 7,840 visual tokens |

Run the immutable fixture check from the retail-intelligence checkout:

```bash
python3 scripts/preflight_smoke_video.py
```

Do not continue unless all five lines report `PASS`.

## View the video yourself

On the DGX Spark desktop, open a terminal in the repository and play the approved file locally:

```bash
ffplay -autoexit -loglevel warning samples/hong-kong-passageway.mp4
```

The expected coarse visual content is a bright indoor shopping passageway with glass storefronts,
a person walking ahead, and forward movement through the passageway. This is a human verification
aid, not exact caption ground truth.

If direct playback is inconvenient, create a Spark-local contact sheet and open it on the Spark
desktop:

```bash
mkdir -p /tmp/ret56-preview
ffmpeg -v error \
  -i samples/hong-kong-passageway.mp4 \
  -vf 'fps=1,scale=480:-1,tile=4x3' \
  -frames:v 1 \
  /tmp/ret56-preview/contact-sheet.jpg
xdg-open /tmp/ret56-preview/contact-sheet.jpg
```

These commands do not upload or copy the video off the DGX Spark.

## Reproduce the standalone service

### 1. Verify the host and Docker GPU access

```bash
uname -m
nvidia-smi
nvidia-container-cli info
docker --version
docker compose version
df -h

docker run --rm --gpus all \
  nvidia/cuda:12.4.0-base-ubuntu22.04 \
  nvidia-smi
```

`uname -m` must report `aarch64`. Keep at least 50 GB free for the RT-VLM image and additional
space for model artifacts.

### 2. Prepare the pinned VSS source

Use a separate working directory rather than adding the NVIDIA checkout to this repository:

```bash
git clone --branch v3.2.1 --depth 1 \
  https://github.com/NVIDIA-AI-Blueprints/video-search-and-summarization.git \
  /absolute/path/to/vss-3.2.1

cd /absolute/path/to/vss-3.2.1/services/rtvi/rt-vlm/docker
```

Create a mode-0600 `.env` that is excluded from Git. Use a current NGC Personal API Key with NGC
Catalog and VSS/model access. Never print, commit, or include the key in logs.

```dotenv
NGC_CLI_API_KEY=<personal-key>
BACKEND_PORT=8018
RTVI_IMAGE=nvcr.io/nvidia/vss-core/vss-rt-vlm:3.2.1-sbsa
VLM_MODEL_TO_USE=cosmos-reason3
MODEL_PATH=ngc:nim/nvidia/cosmos3-nano-reasoner:bf16-final
NGC_API_KEY=${NGC_CLI_API_KEY}
VIA_VLM_API_KEY=${NGC_CLI_API_KEY}
NVIDIA_VISIBLE_DEVICES=0
KAFKA_ENABLED=false
VLM_INPUT_WIDTH=448
VLM_INPUT_HEIGHT=448
VLM_DEFAULT_NUM_FRAMES_PER_SECOND_OR_FIXED_FRAMES_CHUNK=80
VLLM_GPU_MEMORY_UTILIZATION=0.3
```

```bash
chmod 600 .env
docker compose config --quiet
docker pull nvcr.io/nvidia/vss-core/vss-rt-vlm:3.2.1-sbsa
```

The 0.3 memory setting is the tested coexistence value, not a universal optimum. An otherwise idle
Spark may support the image default. This run needed 0.3 because other VSS workloads left 46.94 GiB
free while the default 0.7 setting attempted to reserve 85.18 GiB.

### 3. Start only RT-VLM

The pinned service is named `rtvi-server`. Its Compose file also defines Kafka and Redis, but this
test disables Kafka and must not start or replace brokers belonging to another stack.

```bash
docker compose up -d --no-deps rtvi-server
docker compose ps
docker compose logs -f rtvi-server
```

First startup downloads the model and can take up to 20 minutes. Wait for readiness:

```bash
export BASE_URL=http://localhost:8018
curl -fsS "$BASE_URL/v1/health/ready"
```

Load the secret into the current shell without printing it, then query the live model and version:

```bash
set -a
. ./.env
set +a
export API_KEY="$NGC_CLI_API_KEY"

MODEL_ID=$(
  curl -fsS "$BASE_URL/v1/models" \
    -H "Authorization: Bearer $API_KEY" |
  jq -er '.data[0].id // .id'
)

printf 'Model: %s\n' "$MODEL_ID"
curl -fsS "$BASE_URL/v1/version" | jq
```

### 4. Upload and caption the approved video twice

Set the checkout path and upload the file:

```bash
export RETAIL_REPO=/absolute/path/to/retail-intelligence
export VIDEO_PATH="$RETAIL_REPO/samples/hong-kong-passageway.mp4"

UPLOAD_JSON=$(
  curl -fsS -X POST "$BASE_URL/v1/files" \
    -H "Authorization: Bearer $API_KEY" \
    -F "file=@$VIDEO_PATH" \
    -F 'purpose=vision' \
    -F 'media_type=video'
)

FILE_ID=$(printf '%s' "$UPLOAD_JSON" | jq -er '.id')
printf 'Uploaded file: %s\n' "$FILE_ID"
```

One 12-second chunk covers the entire 10.777-second fixture:

```bash
for RUN_NUMBER in 1 2; do
  jq -n \
    --arg id "$FILE_ID" \
    --arg model "$MODEL_ID" \
    '{
      id: $id,
      model: $model,
      prompt: "Describe only the visible actions and setting in this video. Do not infer identity or intent.",
      chunk_duration: 12,
      stream: false
    }' > "/tmp/ret56-request-${RUN_NUMBER}.json"

  curl -fsS \
    -o "/tmp/ret56-caption-${RUN_NUMBER}.json" \
    -w "Run ${RUN_NUMBER} latency: %{time_total} seconds\n" \
    -X POST "$BASE_URL/v1/generate_captions" \
    -H "Authorization: Bearer $API_KEY" \
    -H 'Content-Type: application/json' \
    --data-binary "@/tmp/ret56-request-${RUN_NUMBER}.json"

  jq -e \
    '(.chunk_responses // []) |
     any(.[]; ((.content // "") | length) > 0)' \
    "/tmp/ret56-caption-${RUN_NUMBER}.json"

  jq -r \
    '.chunk_responses[] | "[\(.start_time)-\(.end_time)] \(.content)"' \
    "/tmp/ret56-caption-${RUN_NUMBER}.json"
done
```

Delete the service-side uploaded copy after the run:

```bash
curl -fsS -X DELETE "$BASE_URL/v1/files/$FILE_ID" \
  -H "Authorization: Bearer $API_KEY"
```

## Observed results

The service reached ready in 211 seconds after the model was cached and the memory setting was
reduced to 0.3. It remained healthy for both calls.

| Check | Result |
|---|---|
| Health | PASS; `docker-rtvi-server-1` healthy on `8018->8000` |
| First inference | PASS; 9.328898 seconds |
| Second inference | PASS; 9.200470 seconds |
| Second run without restart | PASS |
| Non-empty timestamped caption | PASS for both runs |
| Uploaded-copy deletion | PASS |
| Existing VSS stack preserved | PASS |

Run 1 returned:

> [0.0-10.777] A person walks away down a brightly lit, modern hallway with reflective flooring
> and glass storefronts on both sides. The individual moves steadily forward, maintaining a
> consistent pace along the corridor. The environment is quiet, with no other people immediately
> visible nearby. The lighting creates reflections on the polished floor, enhancing the sense of
> depth and movement as the person progresses further into the distance.

Run 2 returned:

> [0.0-10.777] A person is walking down a long, well-lit corridor with shiny tiled floors and glass
> storefronts on both sides. The individual moves steadily forward, maintaining a consistent pace.
> The corridor features modern lighting fixtures embedded in the ceiling, creating a bright and
> reflective environment. Reflections of the person can be seen on the polished floor as they walk
> away from the camera.

Both captions identify the passageway/storefront setting and the person walking ahead. Neither
explicitly describes forward camera movement. The API and inference smoke test therefore passes,
while that part of the coarse semantic expectation remains unconfirmed by these two responses.

## Failures and adjustments

1. Host port 8000 was already occupied by an existing `nat` process. The standalone service used
   host port 8018 without changing the container port or stopping the existing process.
2. The first model download attempt encountered a transient NGC caller-info reachability failure.
   A retry downloaded all 34 files successfully.
3. With existing workloads active, only 46.94 GiB of 121.69 GiB was free for vLLM. The default
   `VLLM_GPU_MEMORY_UTILIZATION=0.7` requested 85.18 GiB and exited before serving. Setting it to
   0.3 allowed RT-VLM to coexist with the running stack.

These conditions are part of the result: isolated component capacity must not be treated as
full-stack capacity. The longer admission, backpressure, restart, and soak gates remain required by
`spec/data-pipeline/agent.md`.

## References

- [Approved sample provenance and expected content](../samples/README.md)
- [One-file vertical slice specification](../spec/vertical-slice/agent.md)
- [Data pipeline specification](../spec/data-pipeline/agent.md)
- [NVIDIA Real-Time VLM documentation](https://docs.nvidia.com/vss/latest/real-time-vlm.html)
- [NVIDIA VSS prerequisites](https://docs.nvidia.com/vss/latest/prerequisites.html)
